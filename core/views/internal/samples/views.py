import json  # <-- Adicionado para o Grafo
import qrcode
import io
import base64
import csv
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required

from core.context import base_context
from core.models import (
    Sample,
    Collection,
    SampleFile,
    Biobank,
    Tag,
    Keyword,
    KeywordValue,
    Bacteria,
    Phage,
    Plasmid,
    HostRange  # <-- Adicionado para o Grafo
)
from core.models.events.model import Event
from core.models.samples.relationship import SampleRelationship

from core.forms import SampleForm, get_form_class_for_sample
from core.permissions.samples import can_view_sample, can_edit_sample, can_delete_sample
from core.permissions.collections import can_edit_collection

# =========================================================
# 1. DASHBOARD (LISTING & FILTERS)
# =========================================================
@login_required
def samples_list_view(request):
    user = request.user
    
    qs = Sample.objects.filter(is_active=True).select_related('biobank', 'owner').prefetch_related('collections').order_by("-created_at")

    query = request.GET.get('q')
    if query:
        qs = qs.filter(
            Q(sample_id__icontains=query) |
            Q(organism_name__icontains=query) |
            Q(sample_type__icontains=query)
        )

    status_filter = request.GET.get('status')
    if status_filter and status_filter not in ['', 'All Statuses']:
        qs = qs.filter(status=status_filter)

    collection_id = request.GET.get('collection')
    if collection_id and collection_id.isdigit():
        qs = qs.filter(collections__id=collection_id)

    ctx = base_context(request)
    ctx.update({
        'samples': qs,
        'filter_collections': Collection.objects.all(),
        'all_samples_for_modal': Sample.objects.filter(is_active=True).values('id', 'sample_id', 'sample_type', 'organism_name'),
    })
    return render(request, "internal/samples/list.html", ctx)


# =========================================================
# 2. CREATE SAMPLE
# =========================================================
@login_required
def sample_create_view(request):
    user = request.user

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_sample":
            try:
                sample_id_base = request.POST.get("sample_id")
                sample_type = request.POST.get("sample_type")
                scientific_notes = request.POST.get("scientific_notes") 
                storage_location = request.POST.get("storage_location", "")
                is_public = request.POST.get("is_public") == "true" or request.POST.get("is_public") == "on"
                
                if sample_type == "Bacterium (Host)":
                    genus = request.POST.get("genus", "").strip()
                    species = request.POST.get("species", "").strip()
                    strain = request.POST.get("strain", "").strip()
                    organism_name = f"{genus} {species} {strain}".strip()
                    
                elif sample_type == "Phage (Virus)":
                    genus = request.POST.get("genus", "").strip()
                    taxonomy = request.POST.get("taxonomy", "").strip()
                    organism_name = f"{genus} {taxonomy}".strip()

                elif sample_type == "Plasmid":
                    construction = request.POST.get("construction_name", "").strip()
                    backbone = request.POST.get("backbone_name", "").strip()
                    organism_name = construction if construction else backbone
                    
                elif sample_type == "Other":
                    organism_name = request.POST.get("custom_organism_name", "Unknown Sample").strip()
                else:
                    organism_name = "Undefined"

                collection_id = request.POST.get("collection")
                collection_obj = Collection.objects.filter(id=collection_id).first() if collection_id else None

                if collection_obj and not can_edit_collection(user, collection_obj):
                    raise PermissionDenied(f"No permission to add samples to collection {collection_obj.name}")

                parent_sample_id_input = request.POST.get("parent_sample_id", "").strip()
                parent_rel_type = request.POST.get("parent_relationship_type", "aliquot")
                parent_sample_obj = None

                if parent_sample_id_input:
                    parent_sample_obj = Sample.objects.filter(sample_id=parent_sample_id_input).first()
                    if not parent_sample_obj:
                        raise ValueError(f"Source sample '{parent_sample_id_input}' not found.")

                biobank_ids = request.POST.getlist("dist_biobank_id[]")
                quantities = request.POST.getlist("dist_quantity[]")

                if not biobank_ids:
                    raise ValueError("No biobank selected.")

                created_samples = []

                with transaction.atomic():
                    for i in range(len(biobank_ids)):
                        bb_id = biobank_ids[i]
                        qty = int(quantities[i]) if quantities[i] else 1
                        biobank = get_object_or_404(Biobank, id=bb_id)

                        for j in range(qty):
                            final_id = sample_id_base if qty == 1 and len(biobank_ids) == 1 else f"{sample_id_base}_{i+1}.{j+1}"

                            if Sample.objects.filter(sample_id=final_id).exists():
                                raise ValueError(f"The ID '{final_id}' already exists in the system.")

                            base_data = {
                                "sample_id": final_id,
                                "organism_name": organism_name, 
                                "sample_type": sample_type,
                                "biobank": biobank,
                                "scientific_notes": scientific_notes,
                                "is_public": is_public,
                                "owner": user,
                                "is_active": True,
                                "status": "pending",
                                "storage_location": storage_location,
                                "collaborator": request.POST.get("collaborator", "").strip()
                            }

                            # BACTERIA
                            if sample_type == "Bacterium (Host)":
                                r_markers = request.POST.get("resistance_markers", "")
                                r_list = [r.strip() for r in r_markers.split(",") if r.strip()]
                                sample = Bacteria.objects.create(
                                    **base_data,
                                    official_name=request.POST.get("official_name", ""),
                                    aliases=request.POST.get("aliases", ""),
                                    genus=request.POST.get("genus", ""),
                                    species=request.POST.get("species", ""),
                                    strain=request.POST.get("strain", ""),
                                    genotype=request.POST.get("genotype", ""),
                                    isolation_source=request.POST.get("isolation_source", ""),
                                    resistance_markers=r_list
                                )

                            # PHAGE
                            elif sample_type == "Phage (Virus)":
                                sample = Phage.objects.create(
                                    **base_data,
                                    official_name=request.POST.get("official_name", ""),
                                    aliases=request.POST.get("aliases", ""),
                                    phage_name=request.POST.get("phage_name", ""),
                                    genus=request.POST.get("genus", ""), 
                                    morphotype=request.POST.get("morphotype"),
                                    taxonomy=request.POST.get("taxonomy"),
                                    lifestyle=request.POST.get("lifestyle"),
                                    isolation_source=request.POST.get("isolation_source"),
                                    isolation_method=request.POST.get("isolation_method"),
                                    genome_type=request.POST.get("genome_type"),
                                    genome_size_bp=request.POST.get("genome_size_bp") or None,
                                    ncbi_accession=request.POST.get("ncbi_accession"),
                                    temp_C=request.POST.get("temp_C") or None
                                )

                            # PLASMID
                            elif sample_type == "Plasmid":
                                r_b_markers = request.POST.get("backbone_resistance_markers", "")
                                r_b_list = [r.strip() for r in r_b_markers.split(",") if r.strip()]
                                
                                r_i_markers = request.POST.get("insert_resistance_markers", "")
                                r_i_list = [r.strip() for r in r_i_markers.split(",") if r.strip()]
                                
                                is_empty = request.POST.get("is_empty_vector") in ["true", "on", "1"]
                                
                                sample = Plasmid.objects.create(
                                    **base_data,
                                    backbone_name=request.POST.get("backbone_name", ""),
                                    backbone_aliases=request.POST.get("backbone_aliases", ""),
                                    vector_type=request.POST.get("vector_type", ""),
                                    induction_system=request.POST.get("induction_system", ""),
                                    origin_of_replication=request.POST.get("origin_of_replication", ""),
                                    backbone_size_bp=request.POST.get("backbone_size_bp") or 0,
                                    backbone_resistance_markers=r_b_list,
                                    is_empty_vector=is_empty,
                                    insert_name=request.POST.get("insert_name", ""),
                                    purpose=request.POST.get("purpose", ""),
                                    insert_size_bp=request.POST.get("insert_size_bp") or 0,
                                    insert_resistance_markers=r_i_list,
                                    construction_name=request.POST.get("construction_name", "")
                                )

                            else:
                                sample = Sample.objects.create(**base_data)
                            
                            # Collections & Parents
                            if collection_obj:
                                sample.collections.add(collection_obj)

                            if parent_sample_obj:
                                SampleRelationship.objects.create(
                                    source_sample=parent_sample_obj,
                                    target_sample=sample,
                                    relationship_type=parent_rel_type,
                                    created_by=user,
                                    notes="Relationship generated automatically during registration."
                                )

                            # Tags & Keywords
                            tag_ids = request.POST.getlist("tags")
                            if tag_ids:
                                sample.tags.set(tag_ids)

                            for raw in request.POST.getlist("keyword_pairs"):
                                if ":::" in raw:
                                    key, value = raw.split(":::")
                                    keyword_obj, _ = Keyword.objects.get_or_create(name=key.strip())
                                    kv, _ = KeywordValue.objects.get_or_create(
                                        keyword=keyword_obj,
                                        value=value.strip()
                                    )
                                    sample.keywords.add(kv)
                                    
                            # =========================================================
                            # RELAÇÕES BIOLÓGICAS (LINHAS DINÂMICAS)
                            # =========================================================
                            host_bacterium_ids = request.POST.getlist("host_bacterium[]")
                            host_bacterium_notes = request.POST.getlist("host_bacterium_notes[]")

                            stored_plasmids_ids = request.POST.getlist("stored_plasmids[]")
                            stored_plasmids_notes = request.POST.getlist("stored_plasmids_notes[]")

                            infecting_phages_ids = request.POST.getlist("infecting_phages[]")
                            infecting_phages_notes = request.POST.getlist("infecting_phages_notes[]")

                            if "Bacterium" in sample_type:
                                for idx, p_id in enumerate(stored_plasmids_ids):
                                    if not p_id.strip(): continue
                                    notes = stored_plasmids_notes[idx] if idx < len(stored_plasmids_notes) else ""
                                    plasmid_obj = Sample.objects.filter(sample_id=p_id.strip()).first()
                                    if plasmid_obj:
                                        SampleRelationship.objects.create(
                                            source_sample=sample, target_sample=plasmid_obj,
                                            relationship_type="STORAGE", created_by=user,
                                            notes=f"Linked during Bacterium registration. Details: {notes}"
                                        )

                                for idx, ph_id in enumerate(infecting_phages_ids):
                                    if not ph_id.strip(): continue
                                    notes = infecting_phages_notes[idx] if idx < len(infecting_phages_notes) else ""
                                    phage_obj = Phage.objects.filter(sample_id=ph_id.strip()).first()
                                    if phage_obj and hasattr(sample, 'bacteria'):
                                        HostRange.objects.update_or_create(
                                            phage=phage_obj, bacteria=sample.bacteria,
                                            defaults={'notes': notes}
                                        )

                            elif "Phage" in sample_type:
                                for idx, h_id in enumerate(host_bacterium_ids):
                                    if not h_id.strip(): continue
                                    notes = host_bacterium_notes[idx] if idx < len(host_bacterium_notes) else ""
                                    bacterium_obj = Bacteria.objects.filter(sample_id=h_id.strip()).first()
                                    if bacterium_obj and hasattr(sample, 'phage'):
                                        HostRange.objects.update_or_create(
                                            phage=sample.phage, bacteria=bacterium_obj,
                                            defaults={'notes': notes}
                                        )

                            elif "Plasmid" in sample_type:
                                for idx, h_id in enumerate(host_bacterium_ids):
                                    if not h_id.strip(): continue
                                    notes = host_bacterium_notes[idx] if idx < len(host_bacterium_notes) else ""
                                    bacterium_obj = Sample.objects.filter(sample_id=h_id.strip()).first()
                                    if bacterium_obj:
                                        SampleRelationship.objects.create(
                                            source_sample=bacterium_obj, target_sample=sample,
                                            relationship_type="STORAGE", created_by=user,
                                            notes=f"Linked during Plasmid registration. Details: {notes}"
                                        )

                            # Log Creation Event
                            Event.objects.create(
                                sample=sample,
                                performed_by=user,
                                event_type="entry",
                                location_snapshot=storage_location,
                                notes=f"Sample registered: {sample.organism_name}."
                            )

                            created_samples.append(sample)

                    # Anexos
                    files = request.FILES.getlist("file")
                    categories = request.POST.getlist("file_category")
                    descriptions = request.POST.getlist("file_description")
                    from core.models.samples.sample import SampleStorageLevel 
                    
                    for sample in created_samples:
                        for k, f in enumerate(files):
                            cat = categories[k] if k < len(categories) else "Other"
                            desc = descriptions[k] if k < len(descriptions) else ""
                            SampleFile.objects.create(sample=sample, file=f, category=cat, description=desc)
                            
                        if storage_location:
                            limpo = storage_location.replace('>', '|').replace(',', '|').replace(';', '|')
                            fatias = [f.strip() for f in limpo.split('|') if f.strip()]
                            for nivel_atual, nome_fatia in enumerate(fatias):
                                SampleStorageLevel.objects.create(sample=sample, name=nome_fatia, level_index=nivel_atual)

                messages.success(request, f"{len(created_samples)} sample(s) registered successfully!")
                return redirect("samples_list")

            except ValueError as ve:
                messages.error(request, str(ve))
            except Exception as e:
                print(f"CRITICAL ERROR CREATE SAMPLE: {e}") 
                messages.error(request, f"Error processing sample: {str(e)}")

    user_biobanks = Biobank.objects.filter(
        Q(owner=user) | Q(is_public=True)
    ).distinct()

    ctx = base_context(request)
    ctx.update({
        "collections": Collection.objects.all(),
        "all_tags": Tag.objects.all(),
        "biobanks": user_biobanks,
        "all_samples": Sample.objects.filter(is_active=True).values('sample_id', 'organism_name', 'sample_type'),
    })
    return render(request, "internal/samples/samples.html", ctx)


# =========================================================
# 3. PRINT & CSV EXPORT
# =========================================================
@login_required
def print_sample_label(request, sample_id):
    sample = get_object_or_404(Sample, id=sample_id)
    if not can_view_sample(request.user, sample):
        raise PermissionDenied

    qr_data = str(sample.uuid)
    qr = qrcode.QRCode(version=1, box_size=10, border=0)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    return render(request, "internal/samples/print_label.html", {'sample': sample, 'qr_code': qr_base64})


@login_required
def export_samples_csv(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig') 
    response['Content-Disposition'] = 'attachment; filename="advanced_samples_report.csv"'
    writer = csv.writer(response, delimiter=';') 
    
    headers = [
        'ID / Barcode', 'Biological Type', 'Organism', 'Status', 'Visibility', 
        'Collections', 'Biobank', 'Storage Location', 'Owner', 'Created At',
        'Phage: Genus', 'Phage: Morphotype', 'Phage: Taxonomy', 'Phage: Lifestyle', 'Genome (Type)', 'Genome Size (bp)',
        'Bacteria: Genus', 'Bacteria: Species', 'Bacteria: Strain', 'Genotype', 'Resistance Markers',
        'Plasmid: Backbone', 'Plasmid: Insert', 'Plasmid Size (bp)'
    ]
    writer.writerow(headers)
    
    samples = Sample.objects.filter(is_active=True).select_related('biobank', 'owner').prefetch_related('collections')
    
    for s in samples:
        cols = ", ".join([c.name for c in s.collections.all()])

        row = [
            s.sample_id, s.sample_type or '', s.organism_name or '', 
            s.get_status_display(), "Public" if s.is_public else "Private", 
            cols, 
            s.biobank.name if s.biobank else '',
            s.storage_location or '',
            s.owner.username, s.created_at.strftime('%Y-%m-%d %H:%M')
        ]
        
        p_genus = morphotype = taxonomy = lifestyle = genome_type = genome_size = ""
        b_genus = species = strain = genotype = resistance = ""
        plasmid_backbone = plasmid_insert = plasmid_size = ""

        if hasattr(s, 'phage'):
            p_genus = s.phage.genus or ""
            morphotype = s.phage.morphotype or ""
            taxonomy = s.phage.taxonomy or ""
            lifestyle = s.phage.lifestyle or ""
            genome_type = s.phage.genome_type or ""
            genome_size = s.phage.genome_size_bp or ""
            
        elif hasattr(s, 'bacteria'):
            b_genus = s.bacteria.genus or ""
            species = s.bacteria.species or ""
            strain = s.bacteria.strain or ""
            genotype = s.bacteria.genotype or ""
            resistance = ", ".join(s.bacteria.resistance_markers) if isinstance(s.bacteria.resistance_markers, list) else s.bacteria.resistance_markers

        elif hasattr(s, 'plasmid'):
            plasmid_backbone = s.plasmid.backbone_name or ""
            plasmid_insert = s.plasmid.insert_name if not s.plasmid.is_empty_vector else "N/A (Empty Vector)"
            plasmid_size = s.plasmid.total_size_bp or ""
            
            b_res = s.plasmid.backbone_resistance_markers or []
            i_res = s.plasmid.insert_resistance_markers or []
            all_res = b_res + i_res
            resistance = ", ".join(all_res) if all_res else ""

        row.extend([
            p_genus, morphotype, taxonomy, lifestyle, genome_type, genome_size,
            b_genus, species, strain, genotype, resistance,
            plasmid_backbone, plasmid_insert, plasmid_size
        ])
        
        writer.writerow(row)
        
    return response

# =========================================================
# 4. EDIT VIEW 
# =========================================================
@login_required
def sample_edit_view(request, sample_id):
    base_sample = get_object_or_404(Sample, id=sample_id)
    
    if hasattr(base_sample, 'bacteria'): real_sample = base_sample.bacteria
    elif hasattr(base_sample, 'phage'): real_sample = base_sample.phage
    elif hasattr(base_sample, 'plasmid'): real_sample = base_sample.plasmid
    else: real_sample = base_sample

    if not can_edit_sample(request.user, real_sample) and not request.user.is_superuser:
        raise PermissionDenied
    
    FormClass = get_form_class_for_sample(real_sample)
    
    if request.method == "POST":
        form = FormClass(request.POST, request.FILES, instance=real_sample)
        if form.is_valid():
            form.save()
            tag_ids = request.POST.getlist("tags")
            if tag_ids:
                real_sample.tags.set(tag_ids)
                
            storage_location = form.cleaned_data.get('storage_location', '')
            from core.models.samples.sample import SampleStorageLevel
            
            SampleStorageLevel.objects.filter(sample=real_sample).delete()
            
            if storage_location:
                limpo = storage_location.replace('>', '|').replace(',', '|').replace(';', '|')
                fatias = [f.strip() for f in limpo.split('|') if f.strip()]
                for nivel_atual, nome_fatia in enumerate(fatias):
                    SampleStorageLevel.objects.create(sample=real_sample, name=nome_fatia, level_index=nivel_atual)
            
            files = request.FILES.getlist("file")
            categories = request.POST.getlist("file_category")
            descriptions = request.POST.getlist("file_description")
            
            for k, f in enumerate(files):
                cat = categories[k] if k < len(categories) else "Other"
                desc = descriptions[k] if k < len(descriptions) else ""
                SampleFile.objects.create(sample=base_sample, file=f, category=cat, description=desc)

            messages.success(request, "Sample updated successfully!")
            return redirect("samples_list")
        else:
            messages.error(request, "Error updating. Please check the fields.")
    else:
        form = FormClass(instance=real_sample)

    parents = base_sample.incoming_relationships.all() 
    children = base_sample.outgoing_relationships.all() 
    sample_files = SampleFile.objects.filter(sample=base_sample).order_by('-uploaded_at')

    # Passa as relações salvas para o frontend renderizar as linhas
    current_host_id = ""
    current_plasmids_string = ""
    current_phages_string = ""

    if hasattr(real_sample, 'phage'):
        hosts = real_sample.host_interactions.all()
        current_host_id = ",".join([h.bacteria.sample_id for h in hosts])
    elif hasattr(real_sample, 'bacteria'):
        phages = real_sample.phage_interactions.all()
        current_phages_string = ",".join([p.phage.sample_id for p in phages])
        plasmids = SampleRelationship.objects.filter(source_sample=real_sample, relationship_type="STORAGE")
        current_plasmids_string = ",".join([p.target_sample.sample_id for p in plasmids])
    elif hasattr(real_sample, 'plasmid'):
        hosts = SampleRelationship.objects.filter(target_sample=real_sample, relationship_type="STORAGE")
        current_host_id = ",".join([h.source_sample.sample_id for h in hosts])

    ctx = base_context(request)
    ctx.update({
        'form': form, 
        'sample': real_sample,
        'parents': parents,
        'children': children,
        'sample_files': sample_files,
        'current_host_id': current_host_id,
        'current_plasmids_string': current_plasmids_string,
        'current_phages_string': current_phages_string
    })
    return render(request, "internal/samples/edit.html", ctx)


# =========================================================
# 5. RELATIONSHIPS 
# =========================================================
@login_required
def sample_relate_view(request, sample_id):
    current_sample = get_object_or_404(Sample, id=sample_id)
    
    if not can_edit_sample(request.user, current_sample) and not request.user.is_superuser:
        raise PermissionDenied

    if request.method == "POST":
        target_ids_str = request.POST.get("target_ids", "")
        target_ids = [tid for tid in target_ids_str.split(",") if tid]
        general_notes = request.POST.get("notes", "")

        if not target_ids:
            messages.warning(request, "No samples selected to relate.")
            return redirect("samples_list")

        try:
            with transaction.atomic():
                for t_id in target_ids:
                    target_sample = Sample.objects.get(id=t_id)
                    if current_sample == target_sample: continue
                    
                    direction = request.POST.get(f"direction_{t_id}") or request.POST.get("direction", "out")
                    rel_type = request.POST.get(f"type_{t_id}") or request.POST.get("relationship_type")
                    eop = request.POST.get(f"eop_{t_id}") or request.POST.get("eop")

                    if direction == "in":
                        source, destination = target_sample, current_sample
                    else:
                        source, destination = current_sample, target_sample

                    SampleRelationship.objects.create(
                        source_sample=source,
                        target_sample=destination,
                        relationship_type=rel_type,
                        notes=general_notes,
                        created_by=request.user
                    )
                    
                    Event.objects.create(
                        sample=current_sample,
                        performed_by=request.user,
                        event_type="update",
                        notes=f"Relationship added: {rel_type} with {target_sample.sample_id}"
                    )

                    if rel_type == "infects":
                        phage_obj = None
                        bacteria_obj = None
                        
                        if hasattr(source, 'phage') and hasattr(destination, 'bacteria'):
                            phage_obj, bacteria_obj = source.phage, destination.bacteria
                        elif hasattr(destination, 'phage') and hasattr(source, 'bacteria'):
                            phage_obj, bacteria_obj = destination.phage, source.bacteria
                            
                        if phage_obj and bacteria_obj:
                            HostRange.objects.update_or_create(
                                phage=phage_obj, bacteria=bacteria_obj,
                                defaults={'efficiency_eop': eop if eop else None}
                            )

            messages.success(request, f"Relationships connected successfully for {len(target_ids)} sample(s)!")
        
        except Exception as e: 
            messages.error(request, f"Error processing relationship: {str(e)}")
            
    return redirect("samples_list")


# =========================================================
# 6. NETWORK GRAPH VIEW
# =========================================================
@login_required
def samples_network_view(request):
    """
    Constrói a estrutura de Nós e Arestas (Nodes & Edges) para o Grafo interativo.
    Lê relacionamentos genéricos (SampleRelationship) e ecológicos (HostRange).
    """
    nodes = []
    edges = []

    # 1. Carrega todos os Samples ativos como NÓS
    samples = Sample.objects.filter(is_active=True).select_related('owner')
    for s in samples:
        # Define a cor/grupo com base no tipo
        group = "generic"
        if "Bacterium" in (s.sample_type or ""): group = "bacteria"
        elif "Phage" in (s.sample_type or ""): group = "phage"
        elif "Plasmid" in (s.sample_type or ""): group = "plasmid"

        nodes.append({
            "id": s.id,
            "label": s.sample_id,
            "title": f"<b>{s.organism_name or 'Unknown'}</b><br>Type: {s.sample_type}<br>Owner: {s.owner.username}",
            "group": group
        })

    # 2. Carrega as Arestas Genéricas (Linhagem, Alíquotas, Storage)
    relationships = SampleRelationship.objects.all()
    for rel in relationships:
        edges.append({
            "from": rel.source_sample_id,
            "to": rel.target_sample_id,
            "label": rel.get_relationship_type_display(),
            "arrows": "to",
            "dashes": True if rel.relationship_type == "STORAGE" else False
        })

    # 3. Carrega as Arestas Ecológicas (HostRange - Fagos infectando Bactérias)
    host_ranges = HostRange.objects.all().select_related('phage', 'bacteria')
    for hr in host_ranges:
        edges.append({
            "from": hr.phage_id,
            "to": hr.bacteria_id,
            "label": "Infects",
            "arrows": "to",
            "color": {"color": "#dc3545"}  # Linha vermelha para infecção
        })

    ctx = base_context(request)
    ctx.update({
        "nodes_json": json.dumps(nodes),
        "edges_json": json.dumps(edges)
    })
    
    return render(request, "internal/samples/network.html", ctx)

/* =========================================================
   SAMPLES PAGE JS - UNIFIED PLASMID & DYNAMIC RELATIONS
========================================================= */

function getCsrfToken() {
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value;
}

// =========================================================
// GLOBAL FUNCTION FOR REPEATERS (BIOLOGICAL INTERACTIONS)
// =========================================================
window.addRelationRow = function(containerId, nameParam, listSourceId, notesPlaceholder) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const row = document.createElement('div');
    row.className = "d-flex gap-2 align-items-center bg-white p-2 border rounded relation-row-item shadow-sm mb-2";
    
    row.innerHTML = `
        <div style="flex: 1;">
            <input type="text" name="${nameParam}" list="${listSourceId}" class="form-control form-control-sm border-success-subtle" placeholder="Search ID..." required autocomplete="off">
        </div>
        <div style="flex: 1.5;">
            <input type="text" name="${nameParam.replace('[]', '_notes[]')}" class="form-control form-control-sm" placeholder="${notesPlaceholder}">
        </div>
        <button type="button" class="btn btn-sm btn-outline-danger border-0" onclick="this.closest('.relation-row-item').remove()"><i class="bi bi-trash"></i></button>
    `;
    container.appendChild(row);
};


document.addEventListener("DOMContentLoaded", () => {

    /* --- 0. ELN INITIALIZATION (QUILL) --- */
    let quill = null;
    if(document.getElementById('eln-editor')) {
        quill = new Quill('#eln-editor', { theme: 'snow' });
    }

    /* --- 1. MAIN FORM (Validation & Submit) --- */
    const mainSampleForm = document.getElementById("mainSampleForm");
    if (mainSampleForm) {
        mainSampleForm.addEventListener("submit", function(e) {
            if (quill) {
                const notesInput = document.getElementById("scientific_notes_input");
                if(notesInput) notesInput.value = quill.root.innerHTML;
            }

            const biobankInputs = document.querySelectorAll('input[name="dist_biobank_id[]"]');
            if (biobankInputs.length === 0) {
                e.preventDefault();
                alert("Please add at least one physical Biobank location for storage.");
                return false;
            }
        });
    }

    /* --- 2. TAGS --- */
    function initTagSystem() {
        document.querySelectorAll(".selectable-tag").forEach(chip => {
            if (chip.dataset.bound) return;
            chip.dataset.bound = "true";
            chip.addEventListener("click", function() {
                this.classList.toggle("selected");
                this.classList.toggle("bg-primary");
                this.classList.toggle("text-white");
                updateTagInputs();
            });
        });
    }

    function updateTagInputs() {
        const container = document.getElementById("tagHiddenInputs");
        if (!container) return;
        container.innerHTML = "";
        document.querySelectorAll(".selectable-tag.selected").forEach(chip => {
            const input = document.createElement("input");
            input.type = "hidden";
            input.name = "tags";
            input.value = chip.dataset.tagId;
            container.appendChild(input);
        });
    }

    function initTagAJAX() {
        const addTagForm = document.getElementById("addTagForm");
        const tagNameInput = document.getElementById("tagNameInput");
        const btnSave = document.getElementById("btnSaveTagAJAX");

        if (addTagForm && btnSave) {
            addTagForm.addEventListener("submit", function(e) {
                e.preventDefault();
                const tagName = tagNameInput.value.trim();
                if (!tagName) return;

                const fd = new FormData();
                fd.append('name', tagName);
                fd.append('csrfmiddlewaretoken', getCsrfToken());

                fetch('/ajax/add_tag/', { method: 'POST', body: fd })
                .then(res => res.json())
                .then(data => {
                    if (data.id) {
                        const container = document.getElementById("tagChipContainer");
                        if (container) {
                            const span = document.createElement("span");
                            span.className = "badge rounded-pill border selectable-tag m-1 p-2 selected bg-primary text-white";
                            span.dataset.tagId = data.id;
                            span.innerText = data.name;
                            span.style.cursor = "pointer";
                            container.appendChild(span);
                        }
                        tagNameInput.value = "";
                        const modal = bootstrap.Modal.getInstance(document.getElementById("addTagModal"));
                        if (modal) modal.hide();
                        initTagSystem();
                        updateTagInputs();
                    }
                });
            });
        }
    }

    /* --- 3. GENERIC KEYWORDS --- */
    function initKeywordSystem() {
        const btnSave = document.getElementById("btnSaveKeywordAJAX");
        if (btnSave) {
            btnSave.onclick = function(e) {
                e.preventDefault();
                const k = document.getElementById("keywordKey").value;
                const v = document.getElementById("keywordValue").value;
                if (!k || !v) return;

                const defaultMsg = document.querySelector('#keywordChipContainer .default-msg');
                if (defaultMsg) defaultMsg.style.display = 'none';

                const chip = document.createElement("span");
                chip.className = "badge bg-light text-dark border p-2 m-1 d-inline-flex align-items-center";
                chip.innerHTML = `<strong>${k}</strong>: ${v} <i class="bi bi-x ms-2 text-danger" style="cursor:pointer;"></i>`;

                const hidden = document.createElement("input");
                hidden.type = "hidden"; 
                hidden.name = "keyword_pairs"; 
                hidden.value = k + ":::" + v;

                chip.querySelector(".bi-x").onclick = () => { 
                    chip.remove(); hidden.remove(); 
                    if(document.querySelectorAll('#keywordChipContainer .badge').length === 0 && defaultMsg) {
                        defaultMsg.style.display = 'block';
                    }
                };
                
                document.getElementById("keywordChipContainer")?.appendChild(chip);
                document.getElementById("keywordHiddenInputs")?.appendChild(hidden);
                
                const modal = bootstrap.Modal.getInstance(document.getElementById("addKeywordModal"));
                if (modal) modal.hide();
                
                document.getElementById("keywordKey").value = ""; 
                document.getElementById("keywordValue").value = "";
            };
        }
    }

    /* --- 4. DYNAMIC STORAGE PATH BUILDER --- */
    function initDynamicStorage() {
        const container = document.getElementById('dynamicStorageContainer');
        const hiddenInput = document.getElementById('storage_location_hidden');
        const textInput = document.getElementById('storageInputVisual');

        if (!container || !textInput) return;

        let levels = [];

        function renderLevels() {
            container.querySelectorAll('.storage-tag-element').forEach(el => el.remove());

            levels.forEach((lvl, index) => {
                const badge = document.createElement('span');
                badge.className = 'badge bg-primary text-white storage-tag-element d-flex align-items-center py-1 px-2 shadow-sm';
                badge.innerHTML = `${lvl} <i class="bi bi-x-circle-fill ms-2" style="cursor:pointer; font-size: 0.85rem;" data-index="${index}"></i>`;
                
                container.insertBefore(badge, textInput);

                const arrow = document.createElement('span');
                arrow.className = 'text-muted storage-tag-element small fw-bold mx-1';
                arrow.innerHTML = '<i class="bi bi-chevron-right"></i>';
                container.insertBefore(arrow, textInput);
            });

            hiddenInput.value = levels.join(" > ");
            textInput.focus();
        }

        window.setStorageLocationFromText = function(value) {
            if (!value) return;
            levels = String(value)
                .replace(/,/g, ">")
                .replace(/;/g, ">")
                .split(">")
                .map(v => v.trim())
                .filter(Boolean);
            renderLevels();
        };

        container.addEventListener('click', (e) => {
            if (e.target.tagName === 'I' && e.target.hasAttribute('data-index')) {
                levels.splice(e.target.dataset.index, 1);
                renderLevels();
            } else {
                textInput.focus();
            }
        });

        textInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                const val = this.value.trim().replace(/,$/, ''); 
                if (val) {
                    levels.push(val);
                    this.value = '';
                    renderLevels();
                }
            } else if (e.key === 'Backspace' && this.value === '' && levels.length > 0) {
                levels.pop();
                renderLevels();
            }
        });
    }

    /* --- 5. BIOBANK DISTRIBUTION --- */
    function initBiobankLogic() {
        const container = document.getElementById('selectedBiobanksContainer');
        const noMsg = document.getElementById('noBiobankMsg');
        const searchInput = document.getElementById('biobankSearch');
        
        if (searchInput) {
            searchInput.addEventListener('input', function(e) {
                const term = e.target.value.toLowerCase();
                document.querySelectorAll('.sheets-option').forEach(opt => {
                    const text = opt.dataset.name.toLowerCase();
                    opt.style.display = text.includes(term) ? 'flex' : 'none';
                });
            });
        }

        document.addEventListener('click', function(e) {
            const addBtn = e.target.closest('.btn-add-bb');
            if (addBtn) {
                e.preventDefault(); e.stopPropagation();
                const opt = addBtn.closest('.sheets-option');
                const bbId = opt.dataset.value;
                const bbName = opt.dataset.name;

                if (container.querySelector(`[data-bb-id="${bbId}"]`)) return;
                if (noMsg) noMsg.style.display = 'none';

                const selectedColId = document.querySelector('select[name="collection"]')?.value || "";

                const row = document.createElement('div');
                row.className = "d-flex align-items-center justify-content-between bg-white border rounded p-3 mb-2 bb-row shadow-sm";
                row.dataset.bbId = bbId;
                row.innerHTML = `
                    <div class="d-flex align-items-center flex-grow-1">
                        <i class="bi bi-building me-3 text-primary fs-5"></i>
                        <div class="flex-grow-1">
                            <span class="fw-bold d-block mb-1">${bbName}</span>
                            <input type="hidden" name="dist_biobank_id[]" value="${bbId}">
                            <input type="hidden" name="dist_collection_id[]" value="${selectedColId}">
                            <div class="d-flex gap-2 align-items-center">
                                <span class="text-muted small">Aliquots Qty:</span>
                                <input type="number" name="dist_quantity[]" class="form-control form-control-sm" value="1" min="1" style="width: 80px;">
                            </div>
                        </div>
                    </div>
                    <button type="button" class="btn btn-link text-danger remove-bb ms-3"><i class="bi bi-trash fs-5"></i></button>
                `;

                container.appendChild(row);
                
                const dropdownBtn = document.getElementById('biobankDropdownBtn');
                if(dropdownBtn) {
                    const bsDropdown = bootstrap.Dropdown.getInstance(dropdownBtn) || new bootstrap.Dropdown(dropdownBtn);
                    bsDropdown.hide();
                }
            }

            const removeBtn = e.target.closest('.remove-bb');
            if (removeBtn) {
                removeBtn.closest('.bb-row').remove();
                if (container.querySelectorAll('.bb-row').length === 0 && noMsg) noMsg.style.display = 'block';
            }
        });
    }

    /* --- 6. DYNAMIC TEMPLATES (EAV) --- */
    function getFieldHTML(field) {
        const label = field.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        
        if (field === 'custom_organism_name') {
             return `
                <label class="section-label text-primary">Organism / Custom Description <span class="text-danger">*</span></label>
                <input type="text" name="${field}" class="form-control form-control-sm border-primary fw-bold" placeholder="Specify what this sample is..." required>
            `;
        }
        if (field === 'is_empty_vector') {
            return `
                <div class="form-check form-switch mt-4">
                    <input class="form-check-input border-info" type="checkbox" role="switch" id="isEmptyVectorSwitch" name="is_empty_vector" value="true" checked>
                    <label class="form-check-label fw-bold text-info-emphasis" for="isEmptyVectorSwitch">This is an Empty Vector (No Insert)</label>
                </div>
            `;
        }
        if (field.includes('sequence')) {
            return `
                <label class="section-label">${label}</label>
                <textarea name="${field}" class="form-control form-control-sm bg-white" placeholder="FASTA sequence..."></textarea>
            `;
        }
        if (field.includes('size_bp')) {
            return `
                <label class="section-label">${label}</label>
                <input type="number" name="${field}" class="form-control form-control-sm bg-white" placeholder="Ex: 4500" min="0">
            `;
        }
        if (field === 'temp_C') {
            return `
                <label class="section-label">${label} (°C)</label>
                <input type="number" step="0.1" name="${field}" class="form-control form-control-sm bg-white" placeholder="Ex: 37.5">
            `;
        }
        if (field === 'morphotype') {
            return `
                <label class="section-label">${label}</label>
                <select name="${field}" class="form-select form-select-sm bg-white">
                    <option value="">Select...</option>
                    <option value="myovirus">Myovirus</option>
                    <option value="siphovirus">Siphovirus</option>
                    <option value="podovirus">Podovirus</option>
                    <option value="other">Other</option>
                </select>
            `;
        }
        if (field === 'lifestyle') {
            return `
                <label class="section-label">${label}</label>
                <select name="${field}" class="form-select form-select-sm bg-white">
                    <option value="">Select...</option>
                    <option value="lytic">Lytic</option>
                    <option value="lysogenic">Lysogenic</option>
                </select>
            `;
        }
        if (field === 'genome_type') {
            return `
                <label class="section-label">${label}</label>
                <select name="${field}" class="form-select form-select-sm bg-white">
                    <option value="">Select...</option>
                    <option value="dsDNA">dsDNA</option>
                    <option value="ssDNA">ssDNA</option>
                    <option value="dsRNA">dsRNA</option>
                    <option value="ssRNA">ssRNA</option>
                </select>
            `;
        }
        if (field === 'vector_type') {
            return `
                <label class="section-label">${label}</label>
                <select name="${field}" class="form-select form-select-sm bg-white">
                    <option value="">Select...</option>
                    <option value="expression">Expression</option>
                    <option value="suicide">Suicide</option>
                    <option value="conjugation">Conjugation</option>
                    <option value="cloning">Cloning</option>
                </select>
            `;
        }
        return `
            <label class="section-label">${label}</label>
            <input type="text" name="${field}" class="form-control form-control-sm bg-white" placeholder="...">
        `;
    }

    function initDynamicTemplates() {
        const typeInput = document.getElementById('sampleTypeInput');
        const container = document.getElementById('dynamicTemplateContainer');
        const fieldsBox = document.getElementById('templateFields');
        const typeNameLabel = document.getElementById('templateTypeName');

        // Biological Relations DOM Elements
        const bioRelSection = document.getElementById('biologicalRelationshipsSection');
        const hostBacteriumDiv = document.getElementById('hostBacteriumDiv');
        const storedPlasmidsDiv = document.getElementById('storedPlasmidsDiv');
        const infectingPhagesDiv = document.getElementById('infectingPhagesDiv');
        const hostHelpText = document.getElementById('hostBacteriumHelp');

        const templates = {
            "Bacterium (Host)": ["official_name", "aliases", "genus", "species", "strain", "genotype", "isolation_source", "resistance_markers"],
            "Phage (Virus)": ["official_name", "aliases", "phage_name", "genus", "morphotype", "taxonomy", "lifestyle", "isolation_source", "isolation_method", "genome_type", "genome_size_bp", "temp_C", "ncbi_accession"],
            "Plasmid": [
                "backbone_name", "backbone_aliases", "vector_type", "induction_system", "origin_of_replication", "backbone_size_bp", "backbone_resistance_markers", 
                "is_empty_vector", "construction_name", "insert_name", "purpose", "insert_size_bp", "insert_resistance_markers"
            ],
            "Other": ["custom_organism_name"]
        };

        if(typeInput && container && fieldsBox) {
            typeInput.addEventListener('change', function() {
                const selectedType = this.value; 
                fieldsBox.innerHTML = ''; 
                
                // 1. Setup EAV Fields
                if (templates[selectedType]) {
                    container.classList.remove('d-none');
                    if (typeNameLabel) typeNameLabel.innerText = selectedType;
                    
                    templates[selectedType].forEach(field => {
                        const col = document.createElement('div');
                        
                        // Custom widths
                        if(field === 'is_empty_vector') {
                            col.className = 'col-md-12 border-bottom pb-3 mb-3';
                        } else if(field.includes('name') || field === 'purpose' || field.includes('markers')) {
                            col.className = 'col-md-4';
                        } else {
                            col.className = 'col-md-3';
                        }

                        // Plasmid Insert Toggling logic class
                        if (selectedType === 'Plasmid' && (field.includes('insert') || field === 'construction_name' || field === 'purpose')) {
                            col.classList.add('plasmid-insert-field', 'd-none');
                        }

                        col.innerHTML = getFieldHTML(field);
                        fieldsBox.appendChild(col);
                    });

                    // Add Listener for Empty Vector Toggle
                    const emptySwitch = document.getElementById('isEmptyVectorSwitch');
                    if (emptySwitch) {
                        emptySwitch.addEventListener('change', function() {
                            const insertFields = document.querySelectorAll('.plasmid-insert-field');
                            insertFields.forEach(el => {
                                if(this.checked) { el.classList.add('d-none'); }
                                else { el.classList.remove('d-none'); }
                            });
                        });
                    }

                } else {
                    container.classList.add('d-none');
                }

                // 2. Setup Biological Relations Visibility
                if(bioRelSection) {
                    bioRelSection.classList.add('d-none');
                    hostBacteriumDiv.classList.add('d-none');
                    storedPlasmidsDiv.classList.add('d-none');
                    infectingPhagesDiv.classList.add('d-none');

                    if(selectedType === 'Bacterium (Host)') {
                        bioRelSection.classList.remove('d-none');
                        storedPlasmidsDiv.classList.remove('d-none');
                        infectingPhagesDiv.classList.remove('d-none');
                    } else if(selectedType === 'Phage (Virus)') {
                        bioRelSection.classList.remove('d-none');
                        hostBacteriumDiv.classList.remove('d-none');
                        hostHelpText.innerText = "Search the bacteria this phage infects.";
                    } else if(selectedType === 'Plasmid') {
                        bioRelSection.classList.remove('d-none');
                        hostBacteriumDiv.classList.remove('d-none');
                        hostHelpText.innerText = "Search the bacteria where this plasmid is stored/propagated.";
                    }
                }
            });
        }
    }

    /* --- 7. AUTO-PREFIXES DYNAMIC --- */
    function initPrefixLogic() {
        const typeInput = document.getElementById('sampleTypeInput');
        const identifierInput = document.getElementById('id_external_identifier');
        const btnGenerate = document.getElementById('btnGenerateAutoId');

        const prefixMap = {
            "Bacterium (Host)": "BAC-",
            "Phage (Virus)": "PHA-",
            "Plasmid": "PLA-",
            "Other": "SMP-"
        };

        if (typeInput && identifierInput && btnGenerate) {
            btnGenerate.addEventListener('click', function() {
                const selectedText = typeInput.value;
                if (!selectedText) {
                    alert("Please select a Sample Type first.");
                    return;
                }
                const prefix = prefixMap[selectedText] || 'SMP-';
                const year = new Date().getFullYear();
                const randomHash = Math.floor(1000 + Math.random() * 9000); 
                identifierInput.value = `${prefix}${year}-${randomHash}`;
            });

            typeInput.addEventListener('change', function() {
                const selectedText = this.value;
                const newPrefix = prefixMap[selectedText] || '';
                const currentValue = identifierInput.value.trim();
                const isJustPrefix = Object.values(prefixMap).some(p => p === currentValue);

                if (currentValue === '' || isJustPrefix) {
                    identifierInput.value = newPrefix;
                }
            });
        }
    }

    /* --- 8. SAMPLE INTAKE PREFILL --- */
    function applySampleIntakePrefill() {
        const script = document.getElementById("sampleIntakePrefillData");
        if (!script) return;

        let data = {};
        try {
            data = JSON.parse(script.textContent || "{}");
        } catch (err) {
            console.warn("Could not parse sample intake prefill data.", err);
            return;
        }

        if (!data || Object.keys(data).length === 0) return;

        function setField(name, value) {
            if (value === undefined || value === null || value === "") return;

            const el = document.getElementsByName(name)[0];
            if (!el) return;

            if (el.type === "checkbox") {
                el.checked = value === true || value === "true" || value === "1" || value === 1 || value === "yes" || value === "sim";
            } else {
                el.value = value;
            }

            el.dispatchEvent(new Event("input", { bubbles: true }));
            el.dispatchEvent(new Event("change", { bubbles: true }));
        }

        const intakeInput = document.getElementById("intake_record_id_input");
        if (intakeInput && data.intake_record_id) {
            intakeInput.value = data.intake_record_id;
        }

        setField("sample_id", data.sample_id);

        const typeInput = document.getElementById("sampleTypeInput");
        if (typeInput && data.sample_type) {
            typeInput.value = data.sample_type;
            typeInput.dispatchEvent(new Event("change", { bubbles: true }));
        }

        setField("custom_organism_name", data.organism_name);
        setField("collaborator", data.provider);
        setField("is_public", data.is_public);

        const collectionSelect = document.getElementsByName("collection")[0];
        if (collectionSelect && data.matched_collection_id) {
            collectionSelect.value = String(data.matched_collection_id);
            collectionSelect.dispatchEvent(new Event("change", { bubbles: true }));
        }

        if (data.storage_location && window.setStorageLocationFromText) {
            window.setStorageLocationFromText(data.storage_location);
        }

        if (data.scientific_notes && quill) {
            quill.root.innerHTML = data.scientific_notes;
        }

        const dynamicFields = [
            "official_name",
            "aliases",
            "genus",
            "species",
            "strain",
            "genotype",
            "isolation_source",
            "resistance_markers",
            "phage_name",
            "morphotype",
            "taxonomy",
            "lifestyle",
            "isolation_method",
            "genome_type",
            "genome_size_bp",
            "temp_C",
            "ncbi_accession",
            "backbone_name",
            "backbone_aliases",
            "vector_type",
            "induction_system",
            "origin_of_replication",
            "backbone_size_bp",
            "backbone_resistance_markers",
            "is_empty_vector",
            "construction_name",
            "insert_name",
            "purpose",
            "insert_size_bp",
            "insert_resistance_markers"
        ];

        dynamicFields.forEach(name => setField(name, data[name]));

        if (data.matched_biobank_id) {
            const btn = document.querySelector(`.sheets-option[data-value="${data.matched_biobank_id}"] .btn-add-bb`);
            if (btn) btn.click();
        }
    }

    // --- INITIALIZATIONS ---
    initTagSystem();
    initTagAJAX();
    initKeywordSystem();
    initDynamicStorage();
    initBiobankLogic();
    initDynamicTemplates();
    initPrefixLogic();
    applySampleIntakePrefill();
});

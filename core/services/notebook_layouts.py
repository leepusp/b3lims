"""Starting layouts (rich HTML bodies) for the built-in entry types.

Each layout is a list of blocks built with the helpers below, so every type
opens with a real structure — a header table, guiding hints, result tables,
numbered procedures — instead of bare headings. Hints are plain ``<p class="b3-hint">``
paragraphs that people overwrite or delete.
"""

from html import escape


def h(title):
    return f"<h2>{escape(title)}</h2>"


def sub(title):
    return f"<h3>{escape(title)}</h3>"


def hint(text):
    return f'<p class="b3-hint"><em>{escape(text)}</em></p>'


def para(text=""):
    return f"<p>{escape(text)}</p>" if text else "<p><br></p>"


def bullets(*items):
    return "<ul>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul>"


def numbered(*items):
    return "<ol>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ol>"


def table(headers, rows=3, prefill=None):
    """Table with a header row and ``rows`` empty rows (or the given prefill rows)."""
    head = "<tr>" + "".join(f"<th>{escape(c)}</th>" for c in headers) + "</tr>"
    body_rows = prefill or [[""] * len(headers) for _ in range(rows)]
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(c) or '<br>'}</td>" for c in row) + "</tr>"
        for row in body_rows
    )
    return f'<table class="b3-tpl"><thead>{head}</thead><tbody>{body}</tbody></table><p><br></p>'


def info(*pairs):
    """Two-column label/value table for the entry header."""
    rows = "".join(
        f"<tr><th>{escape(label)}</th><td><br></td></tr>" for label in pairs
    )
    return f'<table class="b3-tpl b3-info"><tbody>{rows}</tbody></table><p><br></p>'


def section(title, guide=None, *body):
    return h(title) + (hint(guide) if guide else "") + ("".join(body) or para())


def build(*blocks):
    return "".join(blocks)


MATERIALS = ["Item / reagent", "Amount / concentration", "Supplier / lot", "Notes"]
RESULTS = ["Parameter / measurement", "Value", "Unit", "Notes"]
SAFETY_STEPS = (
    "Put on protective equipment and check the safety data sheets.",
    "Prepare and calibrate equipment.",
    "Prepare solutions / samples.",
    "Carry out the work and record raw data as it happens.",
    "Clean the workstation and dispose of waste properly.",
)


def lab_report():
    return build(
        info("Author", "Supervisor", "Institution / lab", "Experiment date", "Lab partner(s)"),
        section("Objective", "State the scientific goal: what is investigated, measured or demonstrated?"),
        section("Theoretical background", "Principles the experiment rests on; cite the literature.",
                sub("Relevant formulas"), bullets("Formula 1: …", "Formula 2: …")),
        section("Materials and equipment", None, table(MATERIALS, 4)),
        section("Experimental procedure", "Step by step, so someone else can reproduce it.",
                sub("Setup"), para(), sub("Procedure steps"), numbered(*SAFETY_STEPS)),
        section("Results and measurements", "Record raw data as unaltered as possible.",
                table(RESULTS, 4), sub("Calculations"), para(), sub("Graphs and diagrams"), para()),
        section("Discussion", "Do the results agree with theory? Which errors exist?",
                sub("Interpretation"), para(), sub("Error analysis"),
                bullets("Systematic errors: …", "Random errors: …")),
        section("Conclusion", "Summarise the key findings and answer the question posed at the start."),
        section("References", None, numbered("Author, A. (Year). Title. Journal, pages.")),
        section("Appendix", None, sub("Raw data"), para(), sub("Additional figures"), para()),
    )


def experiment():
    return build(
        info("Project", "Experiment date", "Collaborators", "Related protocol / entry"),
        section("Objective", "What do you want to find out, and why?"),
        section("Hypothesis", "What do you expect to happen?"),
        section("Experimental design", "Groups, replicates, controls and conditions.",
                table(["Group / condition", "Replicates", "Treatment", "Notes"], 4)),
        section("Observations", "Timestamped notes made during the work.",
                table(["Time", "Observation", "Initials"], 3)),
        section("Results", "Key data, figures and tables. Attach raw files to the entry.",
                table(RESULTS, 3)),
        section("Conclusion", "Was the hypothesis supported? What is the next step?"),
    )


def protocol():
    return build(
        info("Version", "Owner", "Estimated time", "Biosafety level"),
        section("Purpose", "What does this protocol achieve?"),
        section("Scope", "Where it applies and where it does not."),
        section("Safety and prerequisites", "Hazards, protective equipment, training and approvals.",
                bullets("Hazards: …", "Protective equipment: …", "Waste disposal: …")),
        section("Materials and equipment", None, table(MATERIALS, 4)),
        section("Procedure", "Numbered steps with times, temperatures and volumes.", numbered("", "", "")),
        section("Controls and acceptance criteria", "What proves the run worked?"),
        section("Troubleshooting", None, table(["Problem", "Likely cause", "Fix"], 3)),
        section("References", None, numbered("")),
        section("Change notes", None, table(["Version", "Date", "Change", "By"], 2)),
    )


def analysis():
    return build(
        info("Source experiment(s)", "Analyst", "Software / pipeline", "Repository or dataset URL"),
        section("Question", "What should the analysis answer?"),
        section("Data sources", "Where the data comes from and how it was checked.",
                table(["Dataset / file", "Origin", "Checksum or version", "Notes"], 3)),
        section("Analysis plan", "Methods, statistical tests and parameters."),
        section("Results", "Figures and tables, each with a caption and units.", table(RESULTS, 3)),
        section("Interpretation", "What do the results mean and how reliable are they?"),
        section("Conclusion", "Answer the question and note follow-up work."),
    )


def sample_characterization():
    return build(
        info("Sample", "Method / instrument", "Operator", "Measurement date"),
        section("Characterization objective", "Which properties are measured, and why?"),
        section("Sample context", "Origin, storage, preparation and dilution history."),
        section("Measurements", "One row per measurement or replicate.",
                table(["Replicate", "Parameter", "Value", "Unit", "Notes"], 4)),
        section("Quality control", "Calibration, blanks, standards and acceptance criteria.",
                table(["Check", "Expected", "Observed", "Pass?"], 3)),
        section("Results", None),
        section("Interpretation", None),
    )


def plasmid_construction():
    return build(
        info("Backbone", "Insert", "Cloning method", "Resistance marker", "Host strain"),
        section("Design objective", "What construct do you want and what will it be used for?"),
        section("Vector and insert", "Link the Molecular Registry records used.",
                table(["Part", "Registry record", "Size (bp)", "Source / notes"], 3,
                      [["Vector", "", "", ""], ["Insert", "", "", ""], ["Primers", "", "", ""]])),
        section("Assembly strategy", "Method, enzymes or overlaps, reaction setup.",
                table(["Component", "Volume (µL)", "Concentration", "Notes"], 4)),
        section("Transformation and selection", "Strain, recovery, plates and antibiotics."),
        section("Screening results", "Colony PCR or digest per clone.",
                table(["Clone", "Method", "Expected", "Observed", "Keep?"], 4)),
        section("Sequence validation", "Sequencing service, reads and alignment outcome."),
        section("Final construct", "Name, record in the Registry and glycerol stock location."),
    )


def sequencing_bioinformatics():
    return build(
        info("Dataset / accession", "Pipeline and version", "Reference genome", "Analyst"),
        section("Analysis objective", "Biological question and expected outputs."),
        section("Dataset", "Samples, platform, read length and depth.",
                table(["Sample", "Library", "Reads", "Notes"], 3)),
        section("Pipeline", "Tools, versions and parameters (or link to the repository).",
                numbered("", "", "")),
        section("Quality control", "Read quality, mapping rate, duplication, contamination.",
                table(["Metric", "Value", "Threshold", "Pass?"], 3)),
        section("Results", None),
        section("Biological interpretation", None),
        section("Conclusion", None),
    )


def meeting():
    return build(
        info("Date", "Attendees", "Facilitator", "Related project"),
        section("Agenda", None, numbered("", "", "")),
        section("Discussion", "Key points and decisions, by topic."),
        section("Decisions", None, bullets("")),
        section("Action items", None, table(["Action", "Owner", "Due date", "Status"], 3)),
        section("Next meeting", None),
    )


def pcr():
    return build(
        info("Target / gene", "Template", "Polymerase / kit", "Thermocycler"),
        section("Objective", "What is amplified or quantified, and why?"),
        section("Primers", "Link the primer records from the Molecular Registry.",
                table(["Name", "Sequence (5'→3')", "Tm (°C)", "Registry record"], 2)),
        section("Reaction setup", "Per reaction and master mix.",
                table(["Component", "Stock", "Per reaction (µL)", "Master mix (µL)"], 6,
                      [["Buffer", "", "", ""], ["dNTPs", "", "", ""], ["Forward primer", "", "", ""],
                       ["Reverse primer", "", "", ""], ["Polymerase", "", "", ""], ["Template", "", "", ""],
                       ["Water", "", "", ""]])),
        section("Cycling program", None,
                table(["Step", "Temperature (°C)", "Time", "Cycles"], 4,
                      [["Initial denaturation", "", "", "1"], ["Denaturation", "", "", ""],
                       ["Annealing", "", "", ""], ["Extension", "", "", ""], ["Final extension", "", "", "1"]])),
        section("Controls", "No-template, positive and negative controls."),
        section("Results", "Gel image, Ct values or band sizes. Attach the files to this entry.",
                table(["Sample", "Expected", "Observed", "Notes"], 3)),
        section("Conclusion", None),
    )


def cell_culture():
    return build(
        info("Cell line", "Passage number", "Medium / supplements", "Incubator conditions"),
        section("Objective", "Routine maintenance, expansion, treatment or freezing?"),
        section("Observation", "Confluence, morphology, contamination check.",
                table(["Date", "Vessel", "Confluence (%)", "Morphology / notes"], 3)),
        section("Procedure", None,
                numbered("Check cells under the microscope.", "Aspirate medium and wash.",
                         "Detach, count and reseed.", "Label and return to the incubator.")),
        section("Counts and seeding", None,
                table(["Vessel", "Viable cells / mL", "Viability (%)", "Seeded", "Medium (mL)"], 3)),
        section("Treatments", None, table(["Compound", "Concentration", "Time", "Notes"], 3)),
        section("Conclusion and next steps", None),
    )


LAYOUTS = {
    "lab_report": lab_report,
    "experiment": experiment,
    "protocol": protocol,
    "analysis": analysis,
    "sample_characterization": sample_characterization,
    "plasmid_construction": plasmid_construction,
    "sequencing_bioinformatics": sequencing_bioinformatics,
    "meeting": meeting,
    "pcr": pcr,
    "cell_culture": cell_culture,
}


def layout_html(key):
    builder = LAYOUTS.get(key)
    return builder() if builder else ""

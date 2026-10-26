/*
 * Explicit physical movement from Edit Sample.
 * Does not rewrite the existing textual Path Builder.
 */
(() => {
    "use strict";

    function init() {
        const root = document.querySelector(
            "[data-b3-sample-movement-v8146]"
        );

        if (!root) return;

        const assignment = document.getElementById(
            "storageMoveAssignmentV8146"
        );

        const destination = document.getElementById(
            "storageMoveDestinationV8146"
        );

        const position = document.getElementById(
            "storageMovePositionV8146"
        );

        const reason = document.getElementById(
            "storageMoveReasonV8146"
        );

        const submit = document.getElementById(
            "storageMoveSubmitV8146"
        );

        if (
            !assignment || !destination || !position ||
            !reason || !submit
        ) return;

        const expectedLocation = document.getElementById(
            "storageMoveExpectedLocationV8146"
        );

        const expectedPosition = document.getElementById(
            "storageMoveExpectedPositionV8146"
        );

        const expectedSourcePath = document.getElementById(
            "storageMoveExpectedSourcePathV8146"
        );

        const expectedDestinationPath = document.getElementById(
            "storageMoveExpectedDestinationPathV8146"
        );

        const status = document.getElementById(
            "storageMoveStatusV8146"
        );

        function currentOption(select) {
            return select.options[select.selectedIndex] || null;
        }

        function refresh() {
            const source = currentOption(assignment);
            const target = currentOption(destination);

            expectedLocation.value =
                source?.dataset.sourceLocation || "";

            expectedPosition.value =
                source?.dataset.sourcePosition || "";

            expectedSourcePath.value =
                source?.dataset.sourcePath || "";

            expectedDestinationPath.value =
                target?.dataset.destinationPath || "";

            const normalizedPosition =
                position.value.trim().toUpperCase();

            const changed = Boolean(
                target?.value &&
                (
                    target.value !== expectedLocation.value ||
                    normalizedPosition !== expectedPosition.value
                )
            );

            const valid = Boolean(
                source?.value &&
                changed &&
                /^[A-Z]+[0-9]+$/.test(normalizedPosition) &&
                reason.value.trim()
            );

            submit.disabled = !valid;

            status.textContent = valid
                ? "Only this physical assignment will be moved."
                : "Choose a different location or position and provide a reason.";
        }

        assignment.addEventListener("change", () => {
            const source = currentOption(assignment);

            position.value = source?.dataset.sourcePosition || "";
            destination.value = "";
            reason.value = "";

            refresh();
        });

        for (const field of [destination, position, reason]) {
            field.addEventListener("input", refresh);
            field.addEventListener("change", refresh);
        }

        document.addEventListener(
            "b3:storage-child-created-v8146",
            event => {
                const anchor = event.detail?.anchor;
                if (!anchor) return;

                const eligible = ["box", "rack", "other"].includes(
                    String(anchor.location_type).toLowerCase()
                );

                if (!eligible) return;

                const option = document.createElement("option");
                option.value = String(anchor.id);
                option.dataset.destinationPath = anchor.full_path;
                option.textContent =
                    anchor.full_path + " (" + anchor.location_type + ")";

                destination.add(option);
                destination.value = String(anchor.id);
                destination.dispatchEvent(new Event("change"));
            }
        );

        submit.addEventListener("click", () => {
            refresh();

            if (submit.disabled) return;

            const csrf = document.querySelector(
                '#mainSampleForm input[name="csrfmiddlewaretoken"]'
            )?.value;

            if (!csrf || !submit.dataset.moveUrl) {
                status.textContent =
                    "Movement form is unavailable. Reload the page.";
                return;
            }

            const values = {
                csrfmiddlewaretoken: csrf,
                storage_move_assignment_v8146: assignment.value,
                storage_move_destination_v8146: destination.value,
                storage_move_position_v8146:
                    position.value.trim().toUpperCase(),
                storage_move_reason_v8146: reason.value.trim(),
                storage_move_expected_location_v8146:
                    expectedLocation.value,
                storage_move_expected_position_v8146:
                    expectedPosition.value,
                storage_move_expected_source_path_v8146:
                    expectedSourcePath.value,
                storage_move_expected_destination_path_v8146:
                    expectedDestinationPath.value
            };

            const moveForm = document.createElement("form");
            moveForm.method = "POST";
            moveForm.action = submit.dataset.moveUrl;
            moveForm.hidden = true;

            for (const [key, value] of Object.entries(values)) {
                const field = document.createElement("input");
                field.type = "hidden";
                field.name = key;
                field.value = value;
                moveForm.appendChild(field);
            }

            document.body.appendChild(moveForm);
            submit.disabled = true;
            moveForm.submit();
        });

        const initial = currentOption(assignment);
        position.value = initial?.dataset.sourcePosition || "";

        refresh();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

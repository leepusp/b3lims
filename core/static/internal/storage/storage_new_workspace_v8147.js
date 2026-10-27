(() => {
  "use strict";

  const root = document.getElementById("b3-storage-v814");
  if (!root) return;

  const find = id => root.querySelector("#" + id);

  const button = find("b3s-new-storage");
  const dialog = find("b3s-new-storage-dialog");
  const form = find("b3s-new-storage-form");
  const scope = find("b3s-new-storage-scope");
  const groupField = find("b3s-new-storage-group-field");
  const groupSelect = find("b3s-new-storage-group");
  const name = find("b3s-new-storage-name");

  if (
    !button || !dialog || !form ||
    !scope || !groupField || !groupSelect
  ) {
    return;
  }

  function syncGroup() {
    const isGroup = scope.value === "group";

    groupField.hidden = !isGroup;
    groupSelect.disabled = !isGroup;
    groupSelect.required = isGroup;

    if (!isGroup) {
      groupSelect.value = "";
    }
  }

  function openDialog() {
    syncGroup();

    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }

    name?.focus();
  }

  function closeDialog() {
    if (typeof dialog.close === "function") {
      dialog.close();
    } else {
      dialog.removeAttribute("open");
    }
  }

  button.addEventListener("click", openDialog);

  find("b3s-close-new-storage")
    ?.addEventListener("click", closeDialog);

  find("b3s-cancel-new-storage")
    ?.addEventListener("click", closeDialog);

  scope.addEventListener("change", syncGroup);

  form.addEventListener("submit", event => {
    syncGroup();

    if (scope.value === "group" && !groupSelect.value) {
      event.preventDefault();
      groupSelect.focus();
    }
  });

  syncGroup();
})();

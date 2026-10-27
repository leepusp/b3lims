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

  const storageFilter = find("b3s-workspace-filter");
  const physicalData = find("b3s-location-data");
  const emptyNotice = find("b3s-empty-storage");

  const storageRoots = [
    ...root.querySelectorAll(
      "[data-b3s-storage-root]"
    )
  ];

  function syncStorageRoots() {
    if (!storageFilter) return;

    const activeId = storageFilter.value;

    root.dataset.b3sRootSelected =
      activeId ? "1" : "0";

    for (const button of storageRoots) {
      button.setAttribute(
        "aria-pressed",
        String(
          button.dataset.b3sStorageRoot === activeId
        )
      );
    }

    const locations = physicalData
      ? [...physicalData.content.querySelectorAll(
          "span[data-workspace]"
        )]
      : [];

    const hasLocations = locations.some(
      item => item.dataset.workspace === activeId
    );

    const manageable = find("b3s-create-workspace");

    const canManage = Boolean(
      manageable &&
      [...manageable.options].some(
        item => item.value === activeId
      )
    );

    const addLocation = find("b3s-new-location");

    if (addLocation) {
      addLocation.hidden = Boolean(activeId) && !canManage;
    }

    if (emptyNotice) {
      emptyNotice.hidden = !activeId || hasLocations;

      if (!emptyNotice.hidden) {
        emptyNotice.textContent = canManage
          ? "No physical locations yet. Use Add location to create the first root location."
          : "This Storage has no registered physical locations.";
      }
    }
  }

  for (const button of storageRoots) {
    button.addEventListener("click", () => {
      if (!storageFilter) return;

      storageFilter.value =
        button.dataset.b3sStorageRoot;

      storageFilter.dispatchEvent(
        new Event("change", {bubbles: true})
      );
    });
  }

  storageFilter?.addEventListener(
    "change",
    syncStorageRoots
  );

  syncGroup();
  syncStorageRoots();
})();

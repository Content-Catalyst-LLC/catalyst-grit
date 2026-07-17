(function () {
  "use strict";
  var config = window.CatalystGritWorkspace || {};
  var roots = document.querySelectorAll("[data-cg-workspace]");

  function defaultWorkspace() {
    return {
      format: "catalyst-grit-workspace/1.0",
      product_version: config.version || "1.2.0",
      visibility: "private",
      projects: []
    };
  }

  function request(action, workspace) {
    var body = new URLSearchParams();
    body.set("action", action);
    body.set("nonce", config.nonce || "");
    if (workspace !== undefined) body.set("workspace", JSON.stringify(workspace));
    return fetch(config.ajaxUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
      body: body.toString()
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || !data.success) {
          var message = data && data.data && data.data.message ? data.data.message : "Workspace request failed.";
          throw new Error(message);
        }
        return data.data;
      });
    });
  }

  roots.forEach(function (root) {
    var field = root.querySelector("[data-cg-workspace-json]");
    var status = root.querySelector("[data-cg-workspace-status]");
    var load = root.querySelector("[data-cg-workspace-load]");
    var save = root.querySelector("[data-cg-workspace-save]");
    var clear = root.querySelector("[data-cg-workspace-clear]");
    if (!field || !status) return;
    field.value = JSON.stringify(defaultWorkspace(), null, 2);

    function setStatus(message, error) {
      status.textContent = message;
      status.dataset.state = error ? "error" : "ok";
    }

    load.addEventListener("click", function () {
      setStatus("Loading private workspace…", false);
      request("catalyst_grit_workspace_load").then(function (data) {
        field.value = JSON.stringify(data.workspace, null, 2);
        setStatus("Private workspace loaded.", false);
      }).catch(function (error) { setStatus(error.message, true); });
    });

    save.addEventListener("click", function () {
      var value;
      try { value = JSON.parse(field.value); } catch (error) { setStatus("Workspace JSON is invalid.", true); return; }
      if (value.format !== "catalyst-grit-workspace/1.0") { setStatus("Workspace format must be catalyst-grit-workspace/1.0.", true); return; }
      if ((value.visibility || "private") !== "private") { setStatus("Workspace visibility must remain private.", true); return; }
      if (new Blob([JSON.stringify(value)]).size > Number(config.maxBytes || 524288)) { setStatus("Workspace exceeds the 512 KB account-storage limit.", true); return; }
      value.visibility = "private";
      setStatus("Saving private workspace…", false);
      request("catalyst_grit_workspace_save", value).then(function (data) {
        setStatus(data.message || "Private workspace saved.", false);
      }).catch(function (error) { setStatus(error.message, true); });
    });

    clear.addEventListener("click", function () {
      if (!window.confirm("Delete the saved private Catalyst Grit workspace for this account?")) return;
      request("catalyst_grit_workspace_clear").then(function (data) {
        field.value = JSON.stringify(defaultWorkspace(), null, 2);
        setStatus(data.message || "Saved workspace deleted.", false);
      }).catch(function (error) { setStatus(error.message, true); });
    });
  });
}());

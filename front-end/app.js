(function () {
  const cfg = window.APP_CONFIG;

  // Use the API Gateway generated SDK (SDK1) when it is loaded.
  const sdk = (typeof apigClientFactory !== "undefined")
    ? apigClientFactory.newClient({ apiKey: cfg.API_KEY })
    : null;
  if (!sdk) console.warn("API Gateway SDK not found in /sdk - falling back to fetch()");

  const $ = (id) => document.getElementById(id);

  function setStatus(el, msg, kind) {
    el.textContent = msg;
    el.className = "status" + (kind ? " " + kind : "");
  }

  // ---------- Search: GET /search?q= ----------
  async function search(q) {
    if (sdk) {
      const resp = await sdk.searchGet({ q: q }, {}, {});
      return resp.data;
    }
    const resp = await fetch(cfg.API_URL + "/search?q=" + encodeURIComponent(q), {
      headers: { "x-api-key": cfg.API_KEY }
    });
    if (!resp.ok) throw new Error("Search failed: HTTP " + resp.status);
    return resp.json();
  }

  function render(results) {
    const grid = $("results");
    grid.innerHTML = "";
    results.forEach((r) => {
      const card = document.createElement("div");
      card.className = "photo";
      const img = document.createElement("img");
      img.src = r.url;
      img.alt = (r.labels || []).join(", ");
      img.loading = "lazy";
      const labels = document.createElement("div");
      labels.className = "labels";
      labels.textContent = (r.labels || []).join(", ");
      card.appendChild(img);
      card.appendChild(labels);
      grid.appendChild(card);
    });
  }

  $("search-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = $("search-input").value.trim();
    const status = $("search-status");
    if (!q) return;
    setStatus(status, "Searching...");
    $("results").innerHTML = "";
    try {
      const data = await search(q);
      const results = (data && data.results) || [];
      render(results);
      setStatus(status, results.length
        ? results.length + " photo(s) found."
        : "No photos matched \"" + q + "\".", results.length ? "ok" : "");
    } catch (err) {
      console.error(err);
      setStatus(status, "Search error: " + (err.message || err), "error");
    }
  });

  // ---------- Upload: PUT /photos/{object} ----------
  // Raw binary upload is done with fetch(): the generated SDK JSON-serialises
  // request bodies, which corrupts image files.
  function safeName(name) {
    const base = name.replace(/\.[^.]*$/, "").replace(/[^A-Za-z0-9_-]+/g, "_");
    return Date.now() + "-" + (base || "photo") + ".jpg";
  }

  // Re-encode any image (HEIC/AVIF/WebP/PNG/JPEG) to a real JPEG so
  // Rekognition can always read it.
  async function toJpeg(file) {
    const bitmap = await createImageBitmap(file);
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext("2d").drawImage(bitmap, 0, 0);
    return new Promise((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("JPEG conversion failed"))),
        "image/jpeg", 0.92));
  }

  $("upload-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = $("file-input").files[0];
    const status = $("upload-status");
    if (!file) return;

    const labels = $("labels-input").value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .join(", ");

    const key = safeName(file.name);
    const headers = {
      "Content-Type": "image/jpeg",
      "x-api-key": cfg.API_KEY
    };
    if (labels) headers["x-amz-meta-customLabels"] = labels;

    const btn = e.submitter;
    if (btn) btn.disabled = true;
    setStatus(status, "Uploading " + file.name + "...");
    try {
      const jpeg = await toJpeg(file);
      const resp = await fetch(cfg.API_URL + "/photos/" + encodeURIComponent(key), {
        method: "PUT",
        headers: headers,
        body: jpeg
      });
      if (!resp.ok) throw new Error("HTTP " + resp.status + " " + (await resp.text()));
      setStatus(status, "Uploaded as " + key +
        (labels ? " with labels: " + labels : "") +
        ". It will be searchable in a few seconds.", "ok");
      $("upload-form").reset();
    } catch (err) {
      console.error(err);
      setStatus(status, "Upload error: " + (err.message || err), "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  });
})();

// Frontend JavaScript for AI Property Video Generator
document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const form = document.getElementById("generator-form");
  const btnLoadSample = document.getElementById("btn-load-sample");
  const btnSubmit = document.getElementById("btn-submit");
  const dropzone = document.getElementById("image-dropzone");
  const fileInput = document.getElementById("file-input");
  const thumbnailGrid = document.getElementById("thumbnail-grid");
  const photoCounter = document.getElementById("photo-counter");
  const cardProgress = document.getElementById("card-progress");
  const progressStage = document.getElementById("progress-stage");
  const progressFill = document.getElementById("progress-fill");
  const progressMessage = document.getElementById("progress-message");
  const cardResult = document.getElementById("card-result");
  const videoPlayer = document.getElementById("video-player");
  const btnDownload = document.getElementById("btn-download");
  const btnStartNew = document.getElementById("btn-start-new");
  const resultNotices = document.getElementById("result-notices");
  const scriptPreview = document.getElementById("script-preview");
  const btnThemeToggle = document.getElementById("btn-theme-toggle");
  const toastContainer = document.getElementById("toast-container");

  // State
  let uploadedFiles = []; // Array of { id, file, name, previewUrl }
  let currentJobId = null;
  let pollInterval = null;
  let dragSrcIndex = null;

  // --- Theme Toggle (Light default) ---
  let currentTheme = localStorage.getItem("theme") || "light";

  function applyTheme(theme) {
    currentTheme = theme;
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
    if (btnThemeToggle) {
      btnThemeToggle.textContent = theme === "dark" ? "Light Mode" : "Dark Mode";
    }
  }

  applyTheme(currentTheme);

  if (btnThemeToggle) {
    btnThemeToggle.addEventListener("click", () => {
      applyTheme(currentTheme === "dark" ? "light" : "dark");
    });
  }

  // --- Script Mode Segmented Control ---
  const scriptModeInput = document.getElementById("script_mode");
  const segmentBtns = document.querySelectorAll(".segment-btn");

  segmentBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      segmentBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      if (scriptModeInput) {
        scriptModeInput.value = btn.dataset.value;
      }
    });
  });

  // --- Toast Notifications ---
  function showToast(message, isError = false) {
    const toast = document.createElement("div");
    toast.className = `toast ${isError ? "toast-error" : ""}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 200);
    }, 4500);
  }

  // --- Inline Field Errors ---
  function clearErrors() {
    document.querySelectorAll(".field-error").forEach((el) => (el.textContent = ""));
    document.querySelectorAll(".input-error-border").forEach((el) =>
      el.classList.remove("input-error-border")
    );
  }

  function setFieldError(field, message) {
    const errorEl = document.getElementById(`err-${field}`);
    if (errorEl) {
      errorEl.textContent = message;
    }
    const inputEl = document.getElementById(field);
    if (inputEl) {
      inputEl.classList.add("input-error-border");
    }
  }

  // --- Image Handling & Drag/Drop ---
  dropzone.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", (e) => {
    handleFiles(e.target.files);
    fileInput.value = "";
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropzone.classList.add("drag-active");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropzone.classList.remove("drag-active");
    });
  });

  dropzone.addEventListener("drop", (e) => {
    if (e.dataTransfer && e.dataTransfer.files) {
      handleFiles(e.dataTransfer.files);
    }
  });

  function handleFiles(files) {
    clearErrors();
    const allowed = ["image/jpeg", "image/png", "image/webp"];
    Array.from(files).forEach((file) => {
      if (uploadedFiles.length >= 8) {
        showToast("Maximum 8 images allowed. Additional images skipped.");
        return;
      }
      if (!allowed.includes(file.type) && !file.name.match(/\.(jpe?g|png|webp)$/i)) {
        showToast(`Skipped '${file.name}': only JPG, PNG, and WebP are allowed.`, true);
        return;
      }
      if (file.size > 8 * 1024 * 1024) {
        showToast(`Skipped '${file.name}': exceeds 8 MB limit.`, true);
        return;
      }

      uploadedFiles.push({
        id: Math.random().toString(36).substring(2, 9),
        file: file,
        name: file.name,
        previewUrl: URL.createObjectURL(file),
      });
    });

    renderThumbnails();
  }

  function renderThumbnails() {
    thumbnailGrid.innerHTML = "";
    photoCounter.textContent = `${uploadedFiles.length} of 4-8 photos`;

    uploadedFiles.forEach((item, index) => {
      const card = document.createElement("div");
      card.className = "thumb-card";
      card.draggable = true;
      card.dataset.index = index;

      card.innerHTML = `
        <img class="thumb-img" src="${item.previewUrl}" alt="Photo ${index + 1}">
        <span class="thumb-index">#${index + 1}</span>
        <button type="button" class="thumb-remove" title="Remove image" data-index="${index}">×</button>
      `;

      // Drag to Reorder listeners
      card.addEventListener("dragstart", (e) => {
        dragSrcIndex = index;
        card.classList.add("dragging");
        e.dataTransfer.effectAllowed = "move";
      });

      card.addEventListener("dragend", () => {
        card.classList.remove("dragging");
        document.querySelectorAll(".thumb-card").forEach((el) => el.classList.remove("drag-over"));
      });

      card.addEventListener("dragover", (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        card.classList.add("drag-over");
      });

      card.addEventListener("dragleave", () => {
        card.classList.remove("drag-over");
      });

      card.addEventListener("drop", (e) => {
        e.preventDefault();
        card.classList.remove("drag-over");
        if (dragSrcIndex !== null && dragSrcIndex !== index) {
          const moved = uploadedFiles.splice(dragSrcIndex, 1)[0];
          uploadedFiles.splice(index, 0, moved);
          renderThumbnails();
        }
      });

      thumbnailGrid.appendChild(card);
    });

    // Remove buttons
    thumbnailGrid.querySelectorAll(".thumb-remove").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const idx = parseInt(btn.dataset.index, 10);
        const removed = uploadedFiles.splice(idx, 1)[0];
        if (removed && removed.previewUrl) {
          URL.revokeObjectURL(removed.previewUrl);
        }
        renderThumbnails();
      });
    });
  }

  // --- Load Sample Data ---
  btnLoadSample.addEventListener("click", async () => {
    btnLoadSample.disabled = true;
    btnLoadSample.textContent = "Loading sample...";
    try {
      const res = await fetch("/api/sample-data");
      if (!res.ok) throw new Error("Failed to load sample data");
      const sample = await res.json();

      document.getElementById("property_name").value = sample.property_name || "";
      document.getElementById("location").value = sample.location || "";
      document.getElementById("price").value = sample.price || "";
      document.getElementById("property_type").value = sample.property_type || "Apartment";
      document.getElementById("bedrooms").value = sample.bedrooms || "";
      document.getElementById("area").value = sample.area || "";
      document.getElementById("key_features").value = (sample.key_features || []).join("\n");
      document.getElementById("contact_cta").value = sample.contact_cta || "";
      document.getElementById("voiceover_enabled").checked = sample.voiceover_enabled !== false;

      const targetMode = sample.script_mode || "template";
      if (scriptModeInput) scriptModeInput.value = targetMode;
      segmentBtns.forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.value === targetMode);
      });

      // Load sample images
      if (sample.images && sample.images.length > 0) {
        uploadedFiles.forEach((f) => URL.revokeObjectURL(f.previewUrl));
        uploadedFiles = [];

        for (const imgUrl of sample.images) {
          const imgRes = await fetch(imgUrl);
          const blob = await imgRes.blob();
          const filename = imgUrl.split("/").pop() || "sample.jpg";
          const file = new File([blob], filename, { type: blob.type || "image/jpeg" });
          uploadedFiles.push({
            id: Math.random().toString(36).substring(2, 9),
            file: file,
            name: filename,
            previewUrl: URL.createObjectURL(file),
          });
        }
        renderThumbnails();
      }

      clearErrors();
      showToast("Sample data loaded successfully!");
    } catch (err) {
      showToast(err.message || "Could not load sample data", true);
    } finally {
      btnLoadSample.disabled = false;
      btnLoadSample.textContent = "Load sample data";
    }
  });

  // --- Client-side validation ---
  function validateClientSide() {
    clearErrors();
    let hasError = false;

    const name = document.getElementById("property_name").value.trim();
    if (name.length < 2 || name.length > 80) {
      setFieldError("property_name", "Property name must be 2–80 characters");
      hasError = true;
    }

    const loc = document.getElementById("location").value.trim();
    if (loc.length < 2 || loc.length > 120) {
      setFieldError("location", "Location must be 2–120 characters");
      hasError = true;
    }

    const price = document.getElementById("price").value.trim();
    if (!price) {
      setFieldError("price", "Price is required (e.g. ₹85 Lakh or $450,000)");
      hasError = true;
    }

    const type = document.getElementById("property_type").value;
    if (!type) {
      setFieldError("property_type", "Please select a property type");
      hasError = true;
    }

    const features = document
      .getElementById("key_features")
      .value.split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    if (features.length < 3 || features.length > 8) {
      setFieldError("key_features", `Enter 3 to 8 key features (currently ${features.length})`);
      hasError = true;
    }

    const cta = document.getElementById("contact_cta").value.trim();
    if (cta.length < 2 || cta.length > 150) {
      setFieldError("contact_cta", "Contact / CTA text must be 2–150 characters");
      hasError = true;
    }

    if (uploadedFiles.length < 4 || uploadedFiles.length > 8) {
      setFieldError(
        "images",
        `Please upload 4 to 8 photos (currently ${uploadedFiles.length} selected)`
      );
      hasError = true;
    }

    return !hasError;
  }

  // --- Form Submission ---
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!validateClientSide()) return;

    btnSubmit.disabled = true;
    btnSubmit.textContent = "Uploading & Queuing...";

    const formData = new FormData();
    formData.append("property_name", document.getElementById("property_name").value.trim());
    formData.append("location", document.getElementById("location").value.trim());
    formData.append("price", document.getElementById("price").value.trim());
    formData.append("property_type", document.getElementById("property_type").value);
    formData.append("bedrooms", document.getElementById("bedrooms").value.trim());
    formData.append("area", document.getElementById("area").value.trim());
    formData.append("key_features", document.getElementById("key_features").value);
    formData.append("contact_cta", document.getElementById("contact_cta").value.trim());
    formData.append("voiceover_enabled", document.getElementById("voiceover_enabled").checked);

    const scriptMode = scriptModeInput ? scriptModeInput.value : "template";
    formData.append("script_mode", scriptMode);

    // Append images
    uploadedFiles.forEach((item) => {
      formData.append("images", item.file, item.name);
    });

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (res.status === 422) {
        // Field validation errors
        if (data.errors && Array.isArray(data.errors)) {
          data.errors.forEach((err) => {
            setFieldError(err.field, err.message);
          });
          showToast("Please correct the errors highlighted in red.", true);
        } else {
          showToast("Validation failed. Please check your entries.", true);
        }
        btnSubmit.disabled = false;
        btnSubmit.textContent = "Generate Video";
        return;
      }

      if (!res.ok) {
        throw new Error(data.detail || data.message || "Failed to start generation");
      }

      currentJobId = data.job_id;
      startProgressTracking(currentJobId, data.warnings || []);
    } catch (err) {
      showToast(err.message || "Network error. Please try again.", true);
      btnSubmit.disabled = false;
      btnSubmit.textContent = "Generate Video";
    }
  });

  // --- Progress Polling ---
  function startProgressTracking(jobId, initialWarnings) {
    // Hide form, show progress
    form.style.display = "none";
    cardResult.style.display = "none";
    cardProgress.style.display = "flex";

    updateProgress(0, "QUEUED", "Job queued. Preparing renderer...");

    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) {
          throw new Error("Unable to retrieve job status");
        }
        const job = await res.json();
        handleJobUpdate(job, initialWarnings);
      } catch (err) {
        clearInterval(pollInterval);
        showToast(err.message, true);
        resetToForm();
      }
    }, 1000);
  }

  function updateProgress(percent, stage, message) {
    progressFill.style.width = `${percent}%`;
    progressStage.textContent = stage;
    progressMessage.textContent = message;
  }

  function handleJobUpdate(job, initialWarnings) {
    const stageMap = {
      queued: "QUEUED",
      scripting: "SCRIPTING",
      narrating: "VOICE-OVER",
      rendering: "RENDERING",
      done: "COMPLETED",
      error: "ERROR",
    };

    const stageLabel = stageMap[job.status] || job.status.toUpperCase();
    updateProgress(job.progress || 0, stageLabel, job.message || "Processing...");

    if (job.status === "done") {
      clearInterval(pollInterval);
      showResultCard(job, initialWarnings);
    } else if (job.status === "error") {
      clearInterval(pollInterval);
      showToast(job.message || "Rendering failed. Check server logs.", true);
      resetToForm();
    }
  }

  // --- Result View ---
  function showResultCard(job, initialWarnings) {
    cardProgress.style.display = "none";
    cardResult.style.display = "flex";

    // Set video src
    const videoUrl = job.video_url || `/api/jobs/${job.job_id}/video`;
    videoPlayer.src = videoUrl;
    btnDownload.href = videoUrl;

    // Warnings and Notices
    const allWarnings = [...(initialWarnings || []), ...(job.warnings || [])];
    if (job.script && job.script.used_template_fallback) {
      allWarnings.unshift("Notice: Template fallback used (AI script failed fact-check or validation).");
    }

    if (allWarnings.length > 0) {
      resultNotices.style.display = "block";
      resultNotices.innerHTML = allWarnings.map((w) => `<div>⚠️ ${escapeHtml(w)}</div>`).join("");
    } else {
      resultNotices.style.display = "none";
    }

    // Script preview
    if (job.script && job.script.scenes) {
      scriptPreview.textContent = JSON.stringify(job.script, null, 2);
    } else {
      scriptPreview.textContent = "Scene plan generated successfully.";
    }
  }

  function resetToForm() {
    cardProgress.style.display = "none";
    cardResult.style.display = "none";
    form.style.display = "block";
    btnSubmit.disabled = false;
    btnSubmit.textContent = "Generate Video";
  }

  btnStartNew.addEventListener("click", () => {
    videoPlayer.pause();
    videoPlayer.src = "";
    resetToForm();
  });

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});

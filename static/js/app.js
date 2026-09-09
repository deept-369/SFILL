const form = document.getElementById("answer-form");
const editor = document.getElementById("editor");
const feedback = document.getElementById("feedback");
const outputPanel = document.getElementById("output-panel");
const output = document.getElementById("output");
const previousButton = document.getElementById("previous-button");
const submitButton = document.getElementById("submit-button");
const skipButton = document.getElementById("skip-button");
const language =
  document.querySelector(".workspace")?.dataset.language || "python";
const csrfToken = document.querySelector(".workspace")?.dataset.csrfToken;
const apiUrl = (path) => `${path}?language=${encodeURIComponent(language)}`;
const csrfHeaders = csrfToken ? { "X-CSRFToken": csrfToken } : {};

function showFeedback(message, type) {
  feedback.textContent = message;
  feedback.className = `feedback ${type}`;
}

previousButton.addEventListener("click", async () => {
  previousButton.disabled = true;

  try {
    const response = await fetch(apiUrl("/api/previous"), {
      method: "POST",
      headers: csrfHeaders,
    });
    if (!response.ok) {
      throw new Error("Unable to open the previous puzzle.");
    }
    window.location.reload();
  } catch (error) {
    showFeedback(error.message, "incorrect");
    previousButton.disabled = false;
  }
});

skipButton.addEventListener("click", async () => {
  skipButton.disabled = true;
  submitButton.disabled = true;
  showFeedback("Skipping...", "checking");

  try {
    const response = await fetch(apiUrl("/api/skip"), {
      method: "POST",
      headers: csrfHeaders,
    });
    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.message || "Unable to skip the puzzle.");
    }

    showFeedback(result.message, "checking");
    window.setTimeout(() => window.location.reload(), 350);
  } catch (error) {
    showFeedback(error.message, "incorrect");
    skipButton.disabled = false;
    submitButton.disabled = false;
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const answers = [...form.querySelectorAll(".blank")].map((input) =>
    input.value.trim(),
  );

  submitButton.disabled = true;
  showFeedback("Checking...", "checking");

  try {
    const response = await fetch(apiUrl("/api/answer"), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...csrfHeaders },
      body: JSON.stringify({ answers }),
    });
    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.message || "Unable to check the answer.");
    }

    if (!result.correct) {
      showFeedback(result.message, "incorrect");
      submitButton.disabled = false;
      return;
    }

    showFeedback(result.message, "correct");
    output.textContent = result.output;
    outputPanel.hidden = false;

    if (result.completed) {
      submitButton.textContent = "Start again";
      submitButton.disabled = false;
      submitButton.onclick = () => window.location.reload();
      return;
    }

    window.setTimeout(() => window.location.reload(), 650);
  } catch (error) {
    showFeedback(error.message, "incorrect");
    submitButton.disabled = false;
  }
});

editor.querySelector(".blank")?.focus();

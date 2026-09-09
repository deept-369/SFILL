document.querySelectorAll("[data-accent]").forEach((element) => {
  element.style.setProperty("--accent", element.dataset.accent);
});

document.querySelectorAll("[data-width]").forEach((element) => {
  element.style.width = `${element.dataset.width}%`;
});

document.querySelectorAll("[data-color]").forEach((element) => {
  const property = element.dataset.colorProperty || "color";
  element.style.setProperty(property, element.dataset.color);
});

// メニューで画面を切り替える
document.querySelectorAll("nav button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b === button));
    document.querySelectorAll(".screen").forEach((s) => {
      s.classList.toggle("active", s.id === `screen-${button.dataset.screen}`);
    });
  });
});

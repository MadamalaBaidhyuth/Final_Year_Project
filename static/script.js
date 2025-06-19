document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("emailForm");
  const statusMsg = document.getElementById("statusMsg");

  form.addEventListener("submit", () => {
    statusMsg.innerText = "Sending...";
    statusMsg.style.color = "blue";
  });

  const successCount = document.getElementById("sentCount");
  if (successCount && successCount.value) {
    statusMsg.innerText = `Successfully sent ${successCount.value} emails`;
    statusMsg.style.color = "green";
  }
});

// Main JavaScript file for ShadowTalk

// Password toggle functionality
function initPasswordToggles() {
  const passwordToggles = document.querySelectorAll(".toggle-password");

  passwordToggles.forEach((toggle) => {
    toggle.addEventListener("click", function () {
      const passwordInput = this.previousElementSibling;
      const type =
        passwordInput.getAttribute("type") === "password" ? "text" : "password";
      passwordInput.setAttribute("type", type);

      // Toggle icon
      const icon = this.querySelector("i");
      if (type === "text") {
        icon.classList.remove("fa-eye");
        icon.classList.add("fa-eye-slash");
        this.setAttribute("aria-label", "Hide password");
      } else {
        icon.classList.remove("fa-eye-slash");
        icon.classList.add("fa-eye");
        this.setAttribute("aria-label", "Show password");
      }
    });
  });
}

// Initialize when document is ready
document.addEventListener("DOMContentLoaded", function () {
  initTheme();
  initPasswordToggles(); // Add this line
});
// Theme management
function initTheme() {
  const savedTheme = localStorage.getItem("theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);
}

function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute("data-theme");
  const newTheme = currentTheme === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", newTheme);
  localStorage.setItem("theme", newTheme);
}

// Toastr configuration
toastr.options = {
  closeButton: true,
  debug: false,
  newestOnTop: true,
  progressBar: true,
  positionClass: "toast-top-right",
  preventDuplicates: false,
  onclick: null,
  showDuration: "300",
  hideDuration: "1000",
  timeOut: "5000",
  extendedTimeOut: "1000",
  showEasing: "swing",
  hideEasing: "linear",
  showMethod: "fadeIn",
  hideMethod: "fadeOut",
};

// Utility functions
function formatTime(dateString) {
  const date = new Date(dateString);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDuration(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, "0")}:${secs
    .toString()
    .padStart(2, "0")}`;
}

function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// Initialize when document is ready
document.addEventListener("DOMContentLoaded", function () {
  initTheme();

  // Add any global initialization code here
  console.log("ShadowTalk initialized");
});

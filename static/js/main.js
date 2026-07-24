// static/js/main.js
document.addEventListener('DOMContentLoaded', function() {
    const langSelector = document.getElementById('language-selector');
    if (langSelector) {
        langSelector.addEventListener('change', function() {
            const selectedLang = this.value;
            // Get current URL and update/add 'lang' query parameter
            const url = new URL(window.location.href);
            url.searchParams.set('lang', selectedLang);
            window.location.href = url.toString();
        });
    }

    const slotButtons = document.querySelectorAll('.slot-button');
    slotButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Remove 'selected' from all other slots
            slotButtons.forEach(btn => btn.classList.remove('selected'));
            // Add 'selected' to the clicked slot
            this.classList.add('selected');
            // Update a hidden input field with the selected time
            const hiddenTimeInput = document.getElementById('selected_time_slot');
            if (hiddenTimeInput) {
                hiddenTimeInput.value = this.dataset.time; // Assuming data-time attribute holds the time
            }
        });
    });
});

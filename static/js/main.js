// This file can be used for any future client-side interactivity,
// such as date pickers, time slot validation, or dynamic form updates.
// For now, it remains empty as the UI/UX polish focuses on CSS/HTML.

document.addEventListener('DOMContentLoaded', () => {
    // Example: Add a simple date picker functionality (if not using native input[type="date"])
    // Or add logic to dynamically load available time slots based on selected date and service.
    
    const bookingDateInput = document.getElementById('booking_date');
    if (bookingDateInput) {
        // Set min date to today for booking_date input
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, '0'); // Months are 0-indexed
        const dd = String(today.getDate()).padStart(2, '0');
        bookingDateInput.min = `${yyyy}-${mm}-${dd}`;
    }
});
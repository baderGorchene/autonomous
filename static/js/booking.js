document.addEventListener('DOMContentLoaded', () => {
    const serviceSelect = document.getElementById('service_name');
    const bookingDateInput = document.getElementById('booking_date');
    const bookingTimeSelect = document.getElementById('booking_time');
    let selectedServiceDuration = 0; // Global variable to store selected service duration

    const _ = (key) => key; // Placeholder for gettext in JS

    // Set min date for booking_date to today
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0'); // Months are 0-indexed
    const dd = String(today.getDate()).padStart(2, '0');
    bookingDateInput.min = `${yyyy}-${mm}-${dd}`;

    // Event listener for service selection
    if (serviceSelect) {
        serviceSelect.addEventListener('change', () => {
            const selectedOption = serviceSelect.options[serviceSelect.selectedIndex];
            selectedServiceDuration = parseInt(selectedOption.dataset.duration || '0');
            generateTimeSlots();
        });
    }

    // Event listener for date selection
    if (bookingDateInput) {
        bookingDateInput.addEventListener('change', generateTimeSlots);
    }

    function generateTimeSlots() {
        if (!serviceSelect || !bookingDateInput || !bookingTimeSelect) return;

        const selectedDateStr = bookingDateInput.value;
        const selectedService = serviceSelect.value;

        // Clear existing options
        bookingTimeSelect.innerHTML = `<option value="">${_("Choose a time slot")}</option>`;

        if (!selectedDateStr || !selectedService || selectedServiceDuration === 0) {
            return;
        }

        const selectedDate = new Date(selectedDateStr + 'T00:00:00'); // Use T00:00:00 to avoid timezone issues
        const dayOfWeek = selectedDate.toLocaleString('en-US', { weekday: 'long' }); // e.g., "Monday"

        const relevantAvailability = ownerAvailability.filter(slot => slot.day_of_week === dayOfWeek);

        if (relevantAvailability.length === 0) {
            // Optionally, display a message that no availability for this day
            return;
        }

        const now = new Date();
        const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

        relevantAvailability.forEach(slot => {
            let currentSlotTime = new Date(`${selectedDateStr}T${slot.start_time}:00`);
            const endTime = new Date(`${selectedDateStr}T${slot.end_time}:00`);

            while (currentSlotTime.getTime() + selectedServiceDuration * 60 * 1000 <= endTime.getTime()) {
                // Only add slots that are in the future
                if (currentSlotTime > now) {
                    const option = document.createElement('option');
                    const timeString = currentSlotTime.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
                    option.value = timeString;
                    option.textContent = timeString;
                    bookingTimeSelect.appendChild(option);
                }
                currentSlotTime.setMinutes(currentSlotTime.getMinutes() + 30); // Increment by 30 minutes for next slot check
            }
        });
    }

    // Initial generation if a service/date is already selected (e.g., after back button)
    if (serviceSelect && bookingDateInput) {
        const selectedOption = serviceSelect.options[serviceSelect.selectedIndex];
        selectedServiceDuration = parseInt(selectedOption.dataset.duration || '0');
        generateTimeSlots();
    }
});
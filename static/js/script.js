function changeLanguage(lang) {
    const url = new URL(window.location.href);
    url.searchParams.set('lang', lang);
    window.location.href = url.toString();
}

document.addEventListener('DOMContentLoaded', function() {
    const langSelect = document.getElementById('lang-select');
    if (langSelect) {
        langSelect.value = new URLSearchParams(window.location.search).get('lang') || 'en';
        langSelect.addEventListener('change', function() {
            changeLanguage(this.value);
        });
    }

    const serviceSelect = document.getElementById('service');
    const dateInput = document.getElementById('booking_date');
    const timeSelect = document.getElementById('booking_time');

    if (serviceSelect && dateInput && timeSelect) {
        function updateTimeSlots() {
            const selectedServiceId = serviceSelect.value;
            const selectedDate = dateInput.value;
            const ownerAvailability = JSON.parse(document.getElementById('owner-availability').textContent);
            const ownerServices = JSON.parse(document.getElementById('owner-services').textContent);

            timeSelect.innerHTML = '<option value="">{{ _("Select a time") }}</option>';
            if (!selectedDate || !selectedServiceId) {
                return;
            }

            const dayOfWeek = new Date(selectedDate).getDay(); // 0 for Sunday, 1 for Monday...
            const days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
            const dayName = days[dayOfWeek];

            const service = ownerServices.find(s => s.id === parseInt(selectedServiceId));
            if (!service || !ownerAvailability[dayName]) {
                return;
            }
            
            const serviceDuration = service.duration; // in minutes

            ownerAvailability[dayName].forEach(slot => {
                let startHour = parseInt(slot.start.split(':')[0]);
                let startMinute = parseInt(slot.start.split(':')[1]);
                let endHour = parseInt(slot.end.split(':')[0]);
                let endMinute = parseInt(slot.end.split(':')[1]);

                let currentMillis = new Date(selectedDate).setHours(startHour, startMinute, 0, 0);
                let endMillis = new Date(selectedDate).setHours(endHour, endMinute, 0, 0);
                
                while (currentMillis + serviceDuration * 60 * 1000 <= endMillis) {
                    const time = new Date(currentMillis);
                    const formattedTime = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
                    const option = document.createElement('option');
                    option.value = formattedTime;
                    option.textContent = formattedTime;
                    timeSelect.appendChild(option);
                    currentMillis += serviceDuration * 60 * 1000; // Add service duration for next slot
                }
            });
        }

        serviceSelect.addEventListener('change', updateTimeSlots);
        dateInput.addEventListener('change', updateTimeSlots);

        // Set min date for booking to today
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, '0'); // January is 0!
        const dd = String(today.getDate()).padStart(2, '0');
        dateInput.min = `${yyyy}-${mm}-${dd}`;

        updateTimeSlots(); // Initial call to populate times if a date is pre-selected
    }
});
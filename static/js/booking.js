document.addEventListener('DOMContentLoaded', function() {
    const serviceSelect = document.getElementById('service_name');
    const bookingDateInput = document.getElementById('booking_date');
    const bookingTimeSelect = document.getElementById('booking_time');
    const slug = window.location.pathname.split('/')[1]; // Extracts 'their-name' from /their-name/book

    // Set min date to today
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0'); // Months start at 0!
    const dd = String(today.getDate()).padStart(2, '0');
    bookingDateInput.min = `${yyyy}-${mm}-${dd}`;

    function fetchAvailableTimes() {
        const serviceName = serviceSelect.value;
        const bookingDate = bookingDateInput.value;

        if (!serviceName || !bookingDate) {
            bookingTimeSelect.innerHTML = '<option value="">Select a time</option>';
            return;
        }

        // Fetch available times from the backend
        fetch(`/${slug}/available-slots?service_name=${encodeURIComponent(serviceName)}&booking_date=${bookingDate}`)
            .then(response => response.json())
            .then(data => {
                bookingTimeSelect.innerHTML = '<option value="">Select a time</option>';
                if (data.available_slots && data.available_slots.length > 0) {
                    data.available_slots.forEach(slot => {
                        const option = document.createElement('option');
                        option.value = slot;
                        option.textContent = slot;
                        bookingTimeSelect.appendChild(option);
                    });
                } else {
                    const option = document.createElement('option');
                    option.value = '';
                    option.textContent = 'No slots available';
                    bookingTimeSelect.appendChild(option);
                }
            })
            .catch(error => {
                console.error('Error fetching available slots:', error);
                bookingTimeSelect.innerHTML = '<option value="">Error loading times</option>';
            });
    }

    serviceSelect.addEventListener('change', fetchAvailableTimes);
    bookingDateInput.addEventListener('change', fetchAvailableTimes);

    // Initial fetch if service and date are pre-filled (e.g., after a form submission error)
    if (serviceSelect.value && bookingDateInput.value) {
        fetchAvailableTimes();
    }
});
document.addEventListener('DOMContentLoaded', function() {
    const addServiceBtn = document.getElementById('add-service-btn');
    const servicesList = document.getElementById('services-list');
    const servicesJsonInput = document.getElementById('services_json');

    function updateServicesJson() {
        const services = [];
        servicesList.querySelectorAll('.service-item').forEach(item => {
            const name = item.querySelector('[name="service_name[]"]').value;
            const duration = item.querySelector('[name="service_duration[]"]').value;
            const price = item.querySelector('[name="service_price[]"]').value;
            if (name && duration && price) {
                services.push({
                    name: name,
                    duration_minutes: parseInt(duration),
                    price: parseFloat(price)
                });
            }
        });
        servicesJsonInput.value = JSON.stringify(services);
    }

    function addServiceItem(name = '', duration = '', price = '') {
        const div = document.createElement('div');
        div.classList.add('service-item');
        div.innerHTML = `
            <input type="text" name="service_name[]" value="${name}" placeholder="Service Name" required>
            <input type="number" name="service_duration[]" value="${duration}" placeholder="Duration (minutes)" min="5" required>
            <input type="number" name="service_price[]" value="${price}" placeholder="Price" min="0" step="0.01" required>
            <button type="button" class="remove-service-btn">Remove</button>
        `;
        servicesList.appendChild(div);
        div.querySelector('.remove-service-btn').addEventListener('click', function() {
            div.remove();
            updateServicesJson();
        });
        div.querySelectorAll('input').forEach(input => input.addEventListener('change', updateServicesJson));
        updateServicesJson();
    }

    addServiceBtn.addEventListener('click', () => addServiceItem());

    servicesList.querySelectorAll('.service-item').forEach(item => {
        item.querySelector('.remove-service-btn').addEventListener('click', function() {
            item.remove();
            updateServicesJson();
        });
        item.querySelectorAll('input').forEach(input => input.addEventListener('change', updateServicesJson));
    });
    updateServicesJson();

    const availabilitySettings = document.getElementById('availability-settings');
    const availabilityJsonInput = document.getElementById('availability_json');

    function updateAvailabilityJson() {
        const availability = {};
        availabilitySettings.querySelectorAll('.day-availability').forEach(dayDiv => {
            const dayToggle = dayDiv.querySelector('.day-toggle');
            const day = dayToggle.dataset.day;
            const isAvailable = dayToggle.checked;
            const slots = [];

            if (isAvailable) {
                dayDiv.querySelectorAll('.time-slot-item').forEach(slotItem => {
                    const startTime = slotItem.querySelector('.start-time').value;
                    const endTime = slotItem.querySelector('.end-time').value;
                    if (startTime && endTime) {
                        slots.push({ start_time: startTime, end_time: endTime });
                    }
                });
            }
            availability[day] = { is_available: isAvailable, slots: slots };
        });
        availabilityJsonInput.value = JSON.stringify(availability);
    }

    function addTimeSlotItem(day, startTime = '09:00', endTime = '17:00') {
        const slotsDiv = document.getElementById(`slots-${day}`);
        const div = document.createElement('div');
        div.classList.add('time-slot-item');
        div.innerHTML = `
            <input type="time" class="start-time" value="${startTime}" required>
            <input type="time" class="end-time" value="${endTime}" required>
            <button type="button" class="remove-slot-btn">Remove</button>
        `;
        slotsDiv.insertBefore(div, slotsDiv.querySelector('.add-slot-btn'));
        div.querySelector('.remove-slot-btn').addEventListener('click', function() {
            div.remove();
            updateAvailabilityJson();
        });
        div.querySelectorAll('input').forEach(input => input.addEventListener('change', updateAvailabilityJson));
        updateAvailabilityJson();
    }

    availabilitySettings.querySelectorAll('.day-toggle').forEach(toggle => {
        toggle.addEventListener('change', function() {
            const day = this.dataset.day;
            const slotsDiv = document.getElementById(`slots-${day}`);
            if (this.checked) {
                slotsDiv.style.display = 'block';
                if (slotsDiv.querySelectorAll('.time-slot-item').length === 0) {
                    addTimeSlotItem(day);
                }
            } else {
                slotsDiv.style.display = 'none';
            }
            updateAvailabilityJson();
        });
    });

    availabilitySettings.querySelectorAll('.add-slot-btn').forEach(button => {
        button.addEventListener('click', function() {
            const day = this.dataset.day;
            addTimeSlotItem(day);
        });
    });

    availabilitySettings.querySelectorAll('.time-slot-item').forEach(item => {
        item.querySelector('.remove-slot-btn').addEventListener('click', function() {
            item.remove();
            updateAvailabilityJson();
        });
        item.querySelectorAll('input').forEach(input => input.addEventListener('change', updateAvailabilityJson));
    });
    updateAvailabilityJson();

    const profileUpdateForm = document.getElementById('profile-update-form');
    if (profileUpdateForm) {
        profileUpdateForm.addEventListener('submit', function(event) {
            updateServicesJson();
            updateAvailabilityJson();
        });
    }
});

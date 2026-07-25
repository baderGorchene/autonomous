document.addEventListener('DOMContentLoaded', () => {
    // Dashboard functionality for adding/removing services and availability slots
    const servicesList = document.getElementById('services-list');
    const addServiceBtn = document.getElementById('add-service-btn');
    const availabilityList = document.getElementById('availability-list');
    const addAvailabilityBtn = document.getElementById('add-availability-btn');
    const profileForm = document.getElementById('profile-form');

    const _ = (key) => key; // Placeholder for gettext in JS

    // Function to create a new service item
    function createServiceItem(name = '', duration = '', price = '') {
        const div = document.createElement('div');
        div.classList.add('service-item');
        div.innerHTML = `
            <input type="text" name="service_name[]" placeholder="${_('Service Name')}" value="${name}" required>
            <input type="number" name="service_duration[]" placeholder="${_('Duration (minutes)')}" value="${duration}" required>
            <input type="text" name="service_price[]" placeholder="${_('Price (e.g., $50)')}" value="${price}" required>
            <button type="button" class="remove-item-btn">${_('Remove')}</button>
        `;
        return div;
    }

    // Function to create a new availability item
    function createAvailabilityItem(day = '', startTime = '', endTime = '') {
        const div = document.createElement('div');
        div.classList.add('availability-item');
        div.innerHTML = `
            <select name="availability_day[]" required>
                <option value="">${_("Select Day")}</option>
                <option value="Monday" ${day === 'Monday' ? 'selected' : ''}>${_("Monday")}</option>
                <option value="Tuesday" ${day === 'Tuesday' ? 'selected' : ''}>${_("Tuesday")}</option>
                <option value="Wednesday" ${day === 'Wednesday' ? 'selected' : ''}>${_("Wednesday")}</option>
                <option value="Thursday" ${day === 'Thursday' ? 'selected' : ''}>${_("Thursday")}</option>
                <option value="Friday" ${day === 'Friday' ? 'selected' : ''}>${_("Friday")}</option>
                <option value="Saturday" ${day === 'Saturday' ? 'selected' : ''}>${_("Saturday")}</option>
                <option value="Sunday" ${day === 'Sunday' ? 'selected' : ''}>${_("Sunday")}</option>
            </select>
            <input type="time" name="availability_start_time[]" value="${startTime}" required>
            <input type="time" name="availability_end_time[]" value="${endTime}" required>
            <button type="button" class="remove-item-btn">${_('Remove')}</button>
        `;
        return div;
    }

    // Add service button event
    if (addServiceBtn) {
        addServiceBtn.addEventListener('click', () => {
            servicesList.appendChild(createServiceItem());
        });
    }

    // Add availability button event
    if (addAvailabilityBtn) {
        addAvailabilityBtn.addEventListener('click', () => {
            availabilityList.appendChild(createAvailabilityItem());
        });
    }

    // Remove item functionality (delegated event listener)
    if (servicesList) {
        servicesList.addEventListener('click', (event) => {
            if (event.target.classList.contains('remove-item-btn')) {
                event.target.closest('.service-item').remove();
            }
        });
    }
    if (availabilityList) {
        availabilityList.addEventListener('click', (event) => {
            if (event.target.classList.contains('remove-item-btn')) {
                event.target.closest('.availability-item').remove();
            }
        });
    }

    // Form submission handler to serialize services and availability into JSON strings
    if (profileForm) {
        profileForm.addEventListener('submit', (event) => {
            const hiddenServicesInput = document.getElementById('hidden-services-input');
            const hiddenAvailabilityInput = document.getElementById('hidden-availability-input');

            const services = [];
            servicesList.querySelectorAll('.service-item').forEach(item => {
                const name = item.querySelector('input[name="service_name[]"]').value;
                const duration = item.querySelector('input[name="service_duration[]"]').value;
                const price = item.querySelector('input[name="service_price[]"]').value;
                if (name && duration && price) {
                    services.push({ name: name, duration_minutes: parseInt(duration), price: price });
                }
            });
            hiddenServicesInput.value = JSON.stringify(services);

            const availability = [];
            availabilityList.querySelectorAll('.availability-item').forEach(item => {
                const day = item.querySelector('select[name="availability_day[]"]').value;
                const startTime = item.querySelector('input[name="availability_start_time[]"]').value;
                const endTime = item.querySelector('input[name="availability_end_time[]"]').value;
                if (day && startTime && endTime) {
                    availability.push({ day_of_week: day, start_time: startTime, end_time: endTime });
                }
            });
            hiddenAvailabilityInput.value = JSON.stringify(availability);
        });
    }
});
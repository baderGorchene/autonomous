document.addEventListener('DOMContentLoaded', () => {
    const servicesList = document.getElementById('services-list');
    const addServiceBtn = document.getElementById('add-service-btn');
    const hiddenServicesInput = document.getElementById('hidden-services-input');
    const profileForm = document.querySelector('.profile-form');

    const availabilityList = document.getElementById('availability-list');
    const hiddenAvailabilityInput = document.getElementById('hidden-availability-input');

    // Function to update hidden services JSON input
    function updateHiddenServices() {
        const services = [];
        servicesList.querySelectorAll('.service-item').forEach(item => {
            const name = item.querySelector('input[name^="service_name"]').value;
            const duration = item.querySelector('input[name^="service_duration"]').value;
            const price = item.querySelector('input[name^="service_price"]').value;
            const description = item.querySelector('input[name^="service_description"]').value;

            if (name && duration) {
                services.push({
                    name: name,
                    duration: parseInt(duration),
                    price: price ? parseFloat(price) : null,
                    description: description || null
                });
            }
        });
        hiddenServicesInput.value = JSON.stringify(services);
    }

    // Function to add a new service item
    function addServiceItem(name = '', duration = '', price = '', description = '') {
        const div = document.createElement('div');
        div.classList.add('service-item');
        div.innerHTML = `
            <input type="text" name="service_name[]" placeholder="Service Name" value="${name}" required>
            <input type="number" name="service_duration[]" placeholder="Duration (minutes)" value="${duration}" min="10" required>
            <input type="number" name="service_price[]" placeholder="Price (optional)" value="${price}" step="0.01">
            <input type="text" name="service_description[]" placeholder="Description (optional)" value="${description}">
            <button type="button" class="remove-item-btn"><i class="fas fa-trash-alt"></i></button>
        `;
        servicesList.appendChild(div);
        div.querySelector('.remove-item-btn').addEventListener('click', () => {
            div.remove();
            updateHiddenServices();
        });
        div.querySelectorAll('input').forEach(input => input.addEventListener('change', updateHiddenServices));
    }

    // Initialize existing service items with listeners
    servicesList.querySelectorAll('.service-item').forEach(item => {
        item.querySelector('.remove-item-btn').addEventListener('click', () => {
            item.remove();
            updateHiddenServices();
        });
        item.querySelectorAll('input').forEach(input => input.addEventListener('change', updateHiddenServices));
    });

    addServiceBtn.addEventListener('click', () => {
        addServiceItem();
        updateHiddenServices();
    });

    // --- Availability Logic ---
    function updateHiddenAvailability() {
        const availability = {};
        availabilityList.querySelectorAll('.availability-day').forEach(dayDiv => {
            const dayName = dayDiv.querySelector('.time-slots-container').dataset.day;
            const slots = [];
            dayDiv.querySelectorAll('.time-slot-item').forEach(slotItem => {
                const startTime = slotItem.querySelector('input[type="time"][name$="_start[]"]').value;
                const endTime = slotItem.querySelector('input[type="time"][name$="_end[]"]').value;
                if (startTime && endTime) {
                    slots.push({ start_time: startTime, end_time: endTime });
                }
            });
            if (slots.length > 0) {
                availability[dayName] = slots;
            }
        });
        hiddenAvailabilityInput.value = JSON.stringify(availability);
    }

    function addTimeSlotItem(container, day, startTime = '09:00', endTime = '17:00') {
        const div = document.createElement('div');
        div.classList.add('time-slot-item');
        div.innerHTML = `
            <input type="time" name="${day}_start[]" value="${startTime}" required>
            <span>-</span>
            <input type="time" name="${day}_end[]" value="${endTime}" required>
            <button type="button" class="remove-slot-btn"><i class="fas fa-trash-alt"></i></button>
        `;
        container.appendChild(div);
        div.querySelector('.remove-slot-btn').addEventListener('click', () => {
            div.remove();
            updateHiddenAvailability();
        });
        div.querySelectorAll('input').forEach(input => input.addEventListener('change', updateHiddenAvailability));
    }

    // Initialize existing availability items with listeners
    availabilityList.querySelectorAll('.availability-day').forEach(dayDiv => {
        const timeSlotsContainer = dayDiv.querySelector('.time-slots-container');
        const dayName = timeSlotsContainer.dataset.day;

        dayDiv.querySelectorAll('.time-slot-item').forEach(slotItem => {
            slotItem.querySelector('.remove-slot-btn').addEventListener('click', () => {
                slotItem.remove();
                updateHiddenAvailability();
            });
            slotItem.querySelectorAll('input').forEach(input => input.addEventListener('change', updateHiddenAvailability));
        });

        dayDiv.querySelector('.add-slot-btn').addEventListener('click', () => {
            addTimeSlotItem(timeSlotsContainer, dayName);
            updateHiddenAvailability();
        });
    });

    // On form submission, update hidden inputs
    profileForm.addEventListener('submit', (event) => {
        updateHiddenServices();
        updateHiddenAvailability();
    });

    // Initial update of hidden inputs on page load
    updateHiddenServices();
    updateHiddenAvailability();
});

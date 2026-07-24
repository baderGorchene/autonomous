document.addEventListener('DOMContentLoaded', function() {
    const urlParams = new URLSearchParams(window.location.search);
    const currentLang = urlParams.get('lang') || 'en';
    
    document.querySelectorAll('.language-toggle a').forEach(link => {
        const linkLang = new URLSearchParams(link.search).get('lang') || 'en';
        if (linkLang === currentLang) {
            link.style.fontWeight = 'bold';
            link.style.backgroundColor = '#34495e';
        }
    });

    const bookingForm = document.querySelector('.booking-form');
    if (bookingForm) {
        bookingForm.addEventListener('submit', function(event) {
            const service = document.getElementById('service').value;
            const date = document.getElementById('date').value;
            const time = document.getElementById('time').value;
            const customerName = document.getElementById('customer_name').value;
            const customerEmail = document.getElementById('customer_email').value;
            const customerPhone = document.getElementById('customer_phone').value;

            if (!service || !date || !time || !customerName || !customerEmail || !customerPhone) {
                alert('Please fill in all required fields.');
                event.preventDefault();
            }
        });
    }

    const dateInput = document.getElementById('date');
    if (dateInput) {
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, '0');
        const dd = String(today.getDate()).padStart(2, '0');
        dateInput.min = `${yyyy}-${mm}-${dd}`;
    }
});
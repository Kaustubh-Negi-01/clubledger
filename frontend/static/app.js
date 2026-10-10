// Prevent repeated submissions and confirm destructive actions.
document.addEventListener('submit', event => {
    const form = event.target;
    if (form.method === 'dialog') return;
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
        event.preventDefault();
        return;
    }
    if (!form.checkValidity()) return;
    const submit = event.submitter;
    if (submit) {
        submit.setAttribute('aria-busy', 'true');
        setTimeout(() => {
            submit.disabled = true;
            submit.textContent = 'Working…';
        }, 0);
    }
}); // Convert displayed rupees to integer paise and filter fundraiser task choices.
document.addEventListener('DOMContentLoaded', () => {
    const rupee = document.querySelector('[data-rupees]');
    if (rupee) rupee.form.addEventListener('submit', () => {
        document.querySelector('[name="amount_paise"]').value = Math.round(Number(rupee.value) * 100);
    });
    const fundraiser = document.querySelector('[data-fundraiser]'),
        task = document.querySelector('[data-task]');
    if (fundraiser && task) fundraiser.addEventListener('change', () => {
        task.value = '';
        for (const option of task.options) option.hidden = !!option.value && option.dataset.fundraiser !== fundraiser.value;
    });
});
// A single Menu button expands navigation on smaller screens.
document.addEventListener('DOMContentLoaded', () => {
    const button = document.querySelector('.nav-toggle'),
        navigation = document.getElementById('navigation');
    if (!button || !navigation) return;
    const mobile = window.matchMedia('(max-width:800px)');

    function sync() {
        navigation.hidden = mobile.matches;
        button.setAttribute('aria-expanded', String(!navigation.hidden));
    }
    sync();
    mobile.addEventListener('change', sync);
    button.addEventListener('click', () => {
        navigation.hidden = !navigation.hidden;
        button.setAttribute('aria-expanded', String(!navigation.hidden));
    });
});

// Announce the saved payment outcome, trap modal focus and celebrate briefly.
document.addEventListener('DOMContentLoaded', () => {
    const dialog = document.querySelector('[data-payment-result]');
    if (!dialog) return;
    if (typeof dialog.showModal === 'function') {
        dialog.removeAttribute('open');
        dialog.showModal();
    }
    dialog.addEventListener('close', () => {
        const url = new URL(location.href);
        url.searchParams.delete('result');
        history.replaceState(null, '', url);
    });
    if (dialog.dataset.celebrate !== 'true' || window.matchMedia('(prefers-reduced-motion:reduce)').matches) return;
    const confetti = document.createElement('div');
    confetti.className = 'confetti';
    confetti.setAttribute('aria-hidden', 'true');
    dialog.append(confetti);
    // Position and colour come from CSS classes, never inline style attributes.
    for (let i = 0; i < 36; i++) {
        const piece = document.createElement('span');
        piece.className = `confetti-piece-${i+1}`;
        confetti.append(piece);
    }
    const cleanup = setTimeout(() => confetti.remove(), 2400);
    dialog.addEventListener('close', () => {
        clearTimeout(cleanup);
        confetti.remove();
    }, {
        once: true
    });
});

// The error page can return to the previous page without embedding code in HTML.
document.addEventListener('click', (event) => {
    if (event.target.closest('[data-go-back]')) {
        history.back();
    }
});

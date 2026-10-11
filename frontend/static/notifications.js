// Keep the bell usable with keyboard Escape and a click outside its panel.
const notificationMenu = document.querySelector('.notification-menu');
if (notificationMenu) {
    document.addEventListener('click', (event) => {
        if (!notificationMenu.contains(event.target)) notificationMenu.open = false;
    });
    notificationMenu.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            notificationMenu.open = false;
            notificationMenu.querySelector('summary').focus();
        }
    });
}

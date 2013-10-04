$(document).ready(function() {
    $('#maximize-content, #restore-content').click(function(e) {
        $('body').toggleClass('content-maximized');
        e.preventDefault();
        return false;
    });
});

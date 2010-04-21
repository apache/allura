(function($){
    $(function() {
        $('div.reply').each(function() {
            var form = $('form', this).addClass('hidden');
            $('h3', this).click(function() {
                form.toggleClass('hidden');
            });
        });
    });
})(jQuery);

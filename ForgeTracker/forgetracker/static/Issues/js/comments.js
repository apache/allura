(function($){
    $(function() {
        console.log('in comments.js');
        $('div.reply').each(function() {
            var form = $('form', this);
            $('h3', this).click(function() {
                form.toggleClass('hidden');
            });
        });
    });
})(jQuery);
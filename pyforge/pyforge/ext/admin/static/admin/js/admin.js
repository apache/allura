// Setup editable widgets
(function($){
    var edit = '<a href="#" class="edit">Edit</a>';
    var save = '<br/><button class="save">Save</button>';
    $('.editable')
        .find('.viewer').prepend($(edit)).end()
        .find('.editor').append($(save));
    $('.editable .edit').click(function() {
        $(this).closest('.editable')
            .addClass('editing')
            .removeClass('viewing');
        return false;
    });
})(jQuery);

// Setup title-pane widgets
(function($) {
    $('.title-pane .title').click(function() {
        $(this).closest('.title-pane')
            .find('> .content').toggle('fast', function() {
                $(this)
                    .closest('.title-pane').toggleClass('hidden').end()
                    .toggleClass('hidden');
            });
    });
    if(window.location.hash) {
        $(window.location.hash + '.title-pane').removeClass('hidden');
    }
})(jQuery);
(function($) {
    // Setup title-pane widgets
    $('.title-pane .title').click(function() {
        $(this).closest('.title-pane')
            .find('> .content').toggle('fast', function() {
                $(this)
                    .closest('.title-pane').toggleClass('closed').end()
                    .toggleClass('hidden');
            });
    });
    if(window.location.hash) {
        $(window.location.hash + '.title-pane').removeClass('closed');
    }

    // Setup editable widgets
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


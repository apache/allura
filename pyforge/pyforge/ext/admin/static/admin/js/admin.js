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


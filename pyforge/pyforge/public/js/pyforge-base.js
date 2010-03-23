(function($) {
    // Setup title-pane widgets
    $('.title-pane .title').click(function(e) {
        e.preventDefault();
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
    var save = '<br/><input class="save ui-button ui-widget ui-state-default ui-button-text-only" type="submit" value="Save"/>';
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

$(document).ready(function()
{
    $(".defaultText").focus(function(srcc)
    {
        if ($(this).val() == $(this)[0].title)
        {
            $(this).removeClass("defaultTextActive");
            $(this).val("");
        }
    });

    $(".defaultText").blur(function()
    {
        if ($(this).val() == "")
        {
            $(this).addClass("defaultTextActive");
            $(this).val($(this)[0].title);
        }
    });

    $(".defaultText").blur();
});
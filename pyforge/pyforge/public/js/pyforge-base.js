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

    var defocus = function(ele){
        ele.closest('.editable')
                  .addClass('viewing')
                  .removeClass('editing');
        ele.find('input, select, textarea').blur();
    }
    // Setup editable widgets
    $('div.editable, span.editable, h1.editable')
        .find('.viewer').mouseenter(function(e){
            $(this).closest('.editable')
                   .addClass('editing')
                   .removeClass('viewing');
        }).end()
        .find('.editor').mouseleave(function(e){
            defocus($(this));
        })
        .find('input, select, textarea').focus(function(e){
            $(this).closest('.editor').unbind('mouseleave');
            if(this.tagName.toLowerCase() != 'textarea'){
                $(this).keyup(function(e){
                    if(e.keyCode == 13){
                        $(this).closest('form').submit();
                    }
                });
            }
        })
        .change(function(e){
            $(this).closest('form').submit();
        })
        .blur(function(e){
            $(this).closest('.editable').find('.editor').mouseleave(function(e){
                defocus($(this));
            })
            .end()
            .addClass('viewing')
            .removeClass('editing');
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
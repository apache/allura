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
    $('div.editable, span.editable, h1.editable')
        .find('.viewer')
        .append('<button class="edit_btn ui-button ui-widget ui-state-default ui-button-icon-only" title="Edit"><span class="ui-button-icon-primary ui-icon ui-icon-pencil"></span><span class="ui-button-text">Edit</span></button>')
        .click(function(e){
            var editable = $(this).closest('.editable');
            var editor = editable.find('.editor');
            var viewer = editable.find('.viewer');
            if(editor.hasClass('overlap')){
                editor.width(viewer.width());
            }
            editable.addClass('editing')
                    .removeClass('viewing');
            // autoresize textareas will be the wrong size the first time due to being hidden, so nudge them
            editor.find('textarea').change();
            return false;
        })
        .find('a').click(function(event){
          event.stopPropagation();
        })
        .end()
        .end()
        .find('.editor')
        .find('input, select, textarea').each(function(i){
            // we only want one submit button for each editor even if there are multiple inputs
            // make sure the visually important one is first!
            var editor = $(this).closest('.editor');
            if(!$('a.cancel_btn', editor).length){
                var save_btns = $('<div class="save_holder"><input type="submit" value="Save"/><a href="#" class="cancel_btn">Cancel</a></div>');
                if(editor.hasClass('multiline')){
                    var save_holder = editor.find('.save_holder');
                    if(save_holder.length){
                        save_holder.append(save_btns);
                    }
                    else{
                        editor.append(save_btns);
                    }
                }
                else{
                    editor.append($('<table class="holder_table"><tr/></table>')
                                .append($('<td/>').append($(this)))
                                .append($('<td class="save_controls"/>').append($(save_btns)))
                    );
                }
            }
        })
        .end()
        .find('.cancel_btn').click(function(e){
            $(this).closest('.editable')
                      .addClass('viewing')
                      .removeClass('editing');
            return false;
        });
})(jQuery);

$(function(){
    $('.defaultText').
        focus(function(){
            var $this = $(this);
            if ( $this.val() == $this[0].title ){
                $this.removeClass('defaultTextActive').val('');
            }
        }).
        blur(function(){
            var $this = $(this);
            if ( !$this.val() ){
                $this.addClass('defaultTextActive').val($this[0].title);
            }
        }).
        blur();
});

function attach_form_retry( form ){
    $(form).submit(function(){
        $form = $(this);

        var $message = $('#save-message');
        $message.length || ($message = $('<div id="save-message" class="notice"><p>saving...</p></div>').appendTo('body'));
        setTimeout(function(){
            // After 7 seconds, express our concern.
            $message.addClass('error').removeClass('notice').html('<p>The server is taking too long to respond.  Retrying in 30 seconds.</p>');
            setTimeout(function(){
                // After 30 seconds total, give up and try again.
                $message.html('<p>retrying...</p>');
                $form.submit();
            }, 23000)
        }, 7000);
    });
}

$(function(){
    attach_form_retry('form.can-retry');

    // Make life a little better for Chrome users by setting tab-order on inputs.
    // This won't stop Chrome from tabbing over links, but should stop links from
    // coming "in between" fields.
    var i = 0;
    $('input,textarea,select,button').each(function(){
        $(this).attr('tabindex', i++);
    });

    // Provide prompt text for otherwise empty viewers
    var ws = /^\s*$/;
    $('[data-prompt]').each(function(){
        var $this = $(this);
        if ( ws.test($this.text()) ) {
            $this.css('color', 'gray').text($this.attr('data-prompt'))
        }
    });
});

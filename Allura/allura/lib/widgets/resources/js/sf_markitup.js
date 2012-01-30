$(window).load(function() {
    if(!window.markdown_init){
        window.markdown_init = true;
        $('div.markdown_edit').each(function(){
            var $container = $(this);
            var $textarea = $('textarea', $container);
            $textarea.tabby({tabString : "    "});
            var $preview = $('a.markdown_preview', $container);
            var $edit = $('a.markdown_edit', $container);
            var $help = $('a.markdown_help', $container);
            var $preview_area = $('div.markdown_preview', $container);
            var $help_area = $('div.markdown_help', $container);
            var $help_contents = $('div.markdown_help_contents', $container);
            $preview.click(function(evt){
                evt.preventDefault();
                var cval = $.cookie('_session_id');
                $.post('/nf/markdown_to_html', {
                    markdown:$textarea.val(),
                    project:$('input.markdown_project', $container).val(),
                    neighborhood:$('input.markdown_neighborhood', $container).val(),
                    app:$('input.markdown_app', $container).val(),
                    _session_id:cval
                },
                function(resp){
                    $preview_area.html(resp);
                    $preview_area.show();
                    $textarea.hide();
                    $preview.hide();
                    $edit.show();
                });
            });
            $edit.click(function(evt){
                evt.preventDefault();
                $preview_area.hide();
                $textarea.show();
                $preview.show();
                $edit.hide();
            });
            $help.click(function(evt){
                evt.preventDefault();
                $help_contents.html('Loading...');
                $.get($help.attr('href'), function (data) {
                    $help_contents.html(data);
                    var display_section = function(evt) {
                        var $all_sections = $('.markdown_syntax_section', $help_contents);
                        var $this_section = $(location.hash.replace('#', '.'), $help_contents);
                        if ($this_section.length == 0) {
                            $this_section = $('.md_ex_toc', $help_contents);
                        }
                        $all_sections.addClass('hidden_in_modal');
                        $this_section.removeClass('hidden_in_modal');
                        $('.markdown_syntax_toc_crumb').toggle(!$this_section.is('.md_ex_toc'));
                    };
                    $('.markdown_syntax_toc a', $help_contents).click(display_section);
                    $(window).bind('hashchange', display_section); // handle back button
                });
                $help_area.lightbox_me();
            });
            $('.close', $help_area).bind('click', function() {
                $help_area.hide();
            });
        });
    }
});

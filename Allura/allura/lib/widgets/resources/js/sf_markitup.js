/*
       Licensed to the Apache Software Foundation (ASF) under one
       or more contributor license agreements.  See the NOTICE file
       distributed with this work for additional information
       regarding copyright ownership.  The ASF licenses this file
       to you under the Apache License, Version 2.0 (the
       "License"); you may not use this file except in compliance
       with the License.  You may obtain a copy of the License at

         http://www.apache.org/licenses/LICENSE-2.0

       Unless required by applicable law or agreed to in writing,
       software distributed under the License is distributed on an
       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
       KIND, either express or implied.  See the License for the
       specific language governing permissions and limitations
       under the License.
*/

/*global EasyMDE, _replaceSelection, Memorable */
window.CodeMirror = EasyMDE.CodeMirror; // https://github.com/Ionaru/easy-markdown-editor/pull/263
$(window).on('load', function() {
    if(!window.markdown_init){
        window.markdown_init = true;
        $('div.markdown_edit').each(function(){
            var $container = $(this);
            var $textarea = $('textarea', $container);

            var $help_area = $('div.markdown_help', $container);
            var $help_contents = $('div.markdown_help_contents', $container);

            // Override action for a few buttons
            var toolbar = [
              "bold", "italic", "heading", "|", "code",
              "quote", "unordered-list", "ordered-list",
              {
                name: 'table',
                action: drawTable,
                className: 'fa fa-table',
                title: 'Insert Table'
              },
              "horizontal-rule", "|",
              "link", "image",
              "preview",
              //"side-by-side",
              "fullscreen",
              {
                name: 'guide',
                action: show_help,
                className: 'fa fa-question-circle',
                title: 'Formatting Help'
              }
            ];

            var editor = new EasyMDE({
              element: $textarea[0],
              minHeight: "60px",
              autoDownloadFontAwesome: false,
              autofocus: false,
              spellChecker: false, // https://forge-allura.apache.org/p/allura/tickets/7954/
              indentWithTabs: false,
              // contenteditable allows native spellcheck and works fine for desktop browsers and ios (14)
              // but its buggy on android and textarea works better https://github.com/codemirror/CodeMirror/issues/6349 https://github.com/codemirror/CodeMirror/issues/6145
              inputStyle: navigator.userAgent.match(/Android/i) ? 'textarea' : 'contenteditable',
              tabSize: 4,
              toolbar: toolbar,
              previewRender: previewRender,
              parsingConfig: {
                allowAtxHeaderWithoutSpace: true,
                strikethrough: false,
                taskLists: false,
                fencedCodeBlocks: true // override gfm's limited fencing regex
              },
              blockStyles: {
                code: '~~~'
              },
              shortcuts: {
                  "drawLink": null,  // default is cmd-k, used for search in Firefox, better to preserve that
                  "toggleUnorderedList": null, // default is cmd-l, used to activate location bar
              }
            });
            Memorable.add(editor);
            // https://github.com/codemirror/CodeMirror/issues/1576#issuecomment-19146595
            // can't use easymde's shortcuts settings, since those only hook into bindings set up for each button
            editor.codemirror.options.extraKeys.Home = "goLineLeft";
            editor.codemirror.options.extraKeys.End = "goLineRight";

            // user mentions support
            editor.codemirror.on("keyup", function (cm, event) {
              if(event.key === "@" || (event.shiftKey && event.keyCode === 50 /* "2" key */)) {
                CodeMirror.showHint(cm, CodeMirror.hint.alluraUserMentions, {
                  completeSingle: false
                });
              }
            });

            editor.render();

            function drawTable(editor) {
              var cm = editor.codemirror;
              cm.replaceSelection(
                'Header | Header | Header\n' +
                '---------- | ---------- | ------ \n' +
                'Cell      | Cell       | Cell \n' +
                'Cell      | Cell       | Cell ');
              cm.focus();
            }

            function show_help(editor) {
              $help_contents.html('Loading...');
              $.get($help_contents.attr('data-url'), function (data) {
                $help_contents.html(data);
                var display_section = function(evt) {
                  var $all_sections = $('.markdown_syntax_section', $help_contents);
                  var $this_section = $(location.hash.replace('#', '.'), $help_contents);
                  if ($this_section.length === 0) {
                    $this_section = $('.md_ex_toc', $help_contents);
                  }
                  $all_sections.addClass('hidden_in_modal');
                  $this_section.removeClass('hidden_in_modal');
                  $('.markdown_syntax_toc_crumb').toggle(!$this_section.is('.md_ex_toc'));
                };
                $('.markdown_syntax_toc a', $help_contents).click(display_section);
                $(window).on('hashchange', display_section); // handle back button
              });
              $help_area.lightbox_me();
            }

            function previewRender(text, preview) {
              var cval = $.cookie('_session_id');
              $.post('/nf/markdown_to_html', {
                markdown: text,
                project: $('input.markdown_project', $container).val(),
                neighborhood: $('input.markdown_neighborhood', $container).val(),
                app: $('input.markdown_app', $container).val(),
                _session_id: cval
              },
              function(resp) {
                preview.innerHTML = resp;
              });
              return 'Loading...';
            }

            $('.close', $help_area).on('click', function() {
              $help_area.hide();
            });
        });
    }
});

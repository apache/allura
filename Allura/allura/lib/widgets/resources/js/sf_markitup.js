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

$(window).load(function() {
    if(!window.markdown_init){
        window.markdown_init = true;
        $('div.markdown_edit').each(function(){
            var $container = $(this);
            var $textarea = $('textarea', $container);

            var $help_area = $('div.markdown_help', $container);
            var $help_contents = $('div.markdown_help_contents', $container);

            // Override action for "preview" & "guide" tools
            var toolbar = [
              "bold", "italic", "heading", "|",
              {
                name: 'code',
                action: function(editor) { return toggleCodeBlock(editor, '~~~~'); },
                className: 'fa fa-code',
                title: 'Code Block'
              },
              "quote", "unordered-list", "ordered-list",
              {
                name: 'table',
                action: drawTable,
                className: 'fa fa-table',
                title: 'Insert Table'
              },
              "horizontal-rule", "|",
              "link", "image", "|",
              "preview",
              //"side-by-side",
              "fullscreen",
              tool = {
                name: 'guide',
                action: show_help,
                className: 'fa fa-question-circle',
                title: 'Formatting Help'
              }
            ];

            var editor = new SimpleMDE({
              element: $textarea[0],
              autofocus: false,
              spellChecker: false, // https://forge-allura.apache.org/p/allura/tickets/7954/
              indentWithTabs: false,
              tabSize: 4,
              toolbar: toolbar,
              previewRender: previewRender,
              parsingConfig: {
                highlightFormatting: true,
                allowAtxHeaderWithoutSpace: true,
                strikethrough: false,
                taskLists: false,
                fencedCodeBlocks: true // override gfm's limited fencing regex
              }
            });
            editor.render();

            // shared at https://github.com/codemirror/CodeMirror/issues/2143#issuecomment-140100969
            function updateSectionHeaderStyles(cm, change) {
              var lines = cm.lineCount();
              for (var i = Math.max(0, change.from.line-1); i <= Math.min(change.to.line+1, lines-1); i++) {
                var line = cm.getLineHandle(i);
                cm.removeLineClass(line, 'text', 'cm-header');
                cm.removeLineClass(line, 'text', 'cm-header-1');
                cm.removeLineClass(line, 'text', 'cm-header-2');
                var lineTokens = cm.getLineTokens(i);
                var tok = lineTokens[0];
                if (!tok || !tok.type || tok.type.indexOf('header') === -1) {
                  // first token could be some spaces, try 2nd
                  tok = lineTokens[1];
                }
                if (tok && tok.type && tok.type.indexOf('header') !== -1
                  && tok.string !== '#') { // not ATX header style, which starts with #
                  var classes = tok.type.
                    split(' ').
                    filter(function(cls) { return cls.indexOf('header') === 0; }).
                    map(function (cls) { return 'cm-' + cls; }).
                    join(' ');
                  var prev_line = cm.getLineHandle(i-1);
                  cm.addLineClass(prev_line, 'text', classes);
                }
              }
            }
            editor.codemirror.on("change", updateSectionHeaderStyles);
            updateSectionHeaderStyles(editor.codemirror, {from: {line: 0}, to: {line: editor.codemirror.lineCount()}});

            function drawTable(editor) {
              var cm = editor.codemirror;
              _replaceSelection(cm, false, '',
                'Header | Header | Header\n' +
                '---------- | ---------- | ------ \n' +
                'Cell      | Cell       | Cell \n' +
                'Cell      | Cell       | Cell ');
            }

            function toggleCodeBlock(editor, fenceCharsToInsert) {
              // NOTE: this requires highlightFormatting:true in the mode config

              fenceCharsToInsert = fenceCharsToInsert || '```';

              function fencing_line(line) {
                /* return true, if this is a ``` or ~~~ line */
                if (typeof line !== 'object') {
                  throw 'fencing_line() takes a "line" object (not a line number, or line text).  Got: ' + typeof line + ': ' + line;
                }
                return line.styles && line.styles[2] && line.styles[2].indexOf('formatting-code-block') !== -1;
              }

              function code_type(cm, line_num, line, firstTok, lastTok) {
                /*
                 * Return 'single', 'indented', 'fenced' or false
                 *
                 * cm and line_num are required.  Others are optional for efficiency
                 *   To check in the middle of a line, pass in firstTok yourself.
                 */
                line = line || cm.getLineHandle(line_num);
                firstTok = firstTok || cm.getTokenAt({line: line_num, ch: 1});
                lastTok = lastTok || (!!line.text && cm.getTokenAt({line: line_num, ch: line.text.length-1}));
                var types = firstTok.type ? firstTok.type.split(' ') : [];
                if (lastTok && lastTok.state.base.indentedCode) {
                  // have to check last char, since first chars of first line aren't marked as indented
                  return 'indented';
                } else if (types.indexOf('comment') === -1) {
                  // has to be after 'indented' check, since first chars of first indented line aren't marked as such
                  return false;
                } else if (firstTok.state.base.fencedChars || lastTok.state.base.fencedChars || fencing_line(line)) {
                  return 'fenced';
                } else {
                  return 'single';
                }
              }

              function insertFencingAtSelection(cm, cur_start, cur_end, fenceCharsToInsert, inverse) {  // FIXME inverse is just for us
                var start_line_sel = cur_start.line + 1,
                  end_line_sel = cur_end.line + 1,
                  sel_multi = cur_start.line !== cur_end.line,
                  repl_start = (inverse?'':'\n') + fenceCharsToInsert + '\n',  // FIXME extra leading \n for us
                  repl_end = '\n' + fenceCharsToInsert;
                if (sel_multi) {
                  end_line_sel++;
                }
                // handle last char including \n or not
                if (sel_multi && cur_end.ch === 0) {
                  repl_end = fenceCharsToInsert + '\n';
                  end_line_sel--;
                }
                if (inverse) {
                  repl_end = '\n' + repl_end; // FIXME extra leading \n for us
                } else {
                  start_line_sel++; end_line_sel++; // FIXME because of first extra leading \n for us
                }
                _replaceSelection(cm, false, repl_start, repl_end);
                cm.setSelection({line: start_line_sel, ch: 0},
                                {line: end_line_sel, ch: 0});
              }

              var cm = editor.codemirror,
                cur_start = cm.getCursor('start'),
                cur_end = cm.getCursor('end'),
                tok = cm.getTokenAt({line: cur_start.line, ch: cur_start.ch || 1}), // avoid ch 0 which is a cursor pos but not token
                line = cm.getLineHandle(cur_start.line),
                is_code = code_type(cm, cur_start.line, line, tok);
              var block_start, block_end, lineCount;

              if (is_code === 'single') {
                // similar to some SimpleMDE _toggleBlock logic
                var start = line.text.slice(0, cur_start.ch).replace('`',''),
                  end = line.text.slice(cur_start.ch).replace('`', '');
                cm.replaceRange(start + end, {
                  line: cur_start.line,
                  ch: 0
                }, {
                  line: cur_start.line,
                  ch: 99999999999999
                });
                cur_start.ch--;
                if (cur_start !== cur_end) {
                  cur_end.ch--;
                }
                cm.setSelection(cur_start, cur_end);
                cm.focus();
              } else if (is_code === 'fenced') {
                if (cur_start.line !== cur_end.line || cur_start.ch !== cur_end.ch) {
                  // use selection
                  for (block_start = cur_start.line; block_start >= 0; block_start--) {
                    line = cm.getLineHandle(block_start);
                    if (fencing_line(line)) {
                      break;
                    }
                  }
                  var fencedTok = cm.getTokenAt({line: block_start, ch: 1});
                  insertFencingAtSelection(cm, cur_start, cur_end, fencedTok.state.base.fencedChars, true);
                } else {
                  // no selection, search for ends of this fenced block
                  var search_from = cur_start.line;
                  if (fencing_line(cm.getLineHandle(cur_start.line))) {  // gets a little tricky if cursor is right on a fenced line
                    if (code_type(cm, cur_start.line + 1) === 'fenced') {
                      block_start = cur_start.line;
                      search_from = cur_start.line + 1; // for searching for "end"
                    } else {
                      block_end = cur_start.line;
                      search_from = cur_start.line - 1; // for searching for "start"
                    }
                  }
                  if (block_start === undefined) {
                    for (block_start = search_from; block_start >= 0; block_start--) {
                      line = cm.getLineHandle(block_start);
                      if (fencing_line(line)) {
                        break;
                      }
                    }
                  }
                  if (block_end === undefined) {
                    lineCount = cm.lineCount();
                    for (block_end = search_from; block_end < lineCount; block_end++) {
                      line = cm.getLineHandle(block_end);
                      if (fencing_line(line)) {
                        break;
                      }
                    }
                  }
                  cm.operation(function () {
                    cm.replaceRange('', {line: block_start, ch: 0}, {line: block_start + 1, ch: 0});
                    cm.replaceRange('', {line: block_end - 1, ch: 0}, {line: block_end, ch: 0});
                  });
                  cm.focus();
                }
              } else if (is_code === 'indented') {
                if (cur_start.line !== cur_end.line || cur_start.ch !== cur_end.ch) {
                  // use selection
                  block_start = cur_start.line;
                  block_end = cur_end.line;
                  if (cur_end.ch === 0) {
                    block_end--;
                  }
                } else {
                  // no selection, search for ends of this indented block
                  for (block_start = cur_start.line; block_start >= 0; block_start--) {
                    line = cm.getLineHandle(block_start);
                    if (line.text.match(/^\s*$/)) {
                      // empty or all whitespace - keep going
                      continue;
                    } else {
                      if (code_type(cm, block_start, line) !== 'indented') {
                        block_start += 1;
                        break;
                      }
                    }
                  }
                  lineCount = cm.lineCount();
                  for (block_end = cur_start.line; block_end < lineCount; block_end++) {
                    line = cm.getLineHandle(block_end);
                    if (line.text.match(/^\s*$/)) {
                      // empty or all whitespace - keep going
                      continue;
                    } else {
                      if (code_type(cm, block_end, line) !== 'indented') {
                        block_end -= 1;
                        break;
                      }
                    }
                  }
                }
                // if we are going to un-indent based on a selected set of lines, and the next line is indented too, we need to
                // insert a blank line so that the next line(s) continue to be indented code
                var next_line = cm.getLineHandle(block_end+1),
                  next_line_last_tok = next_line && cm.getTokenAt({line: block_end+1, ch: next_line.text.length-1}),
                  next_line_indented = next_line_last_tok && next_line_last_tok.state.base.indentedCode;
                if (next_line_indented) {
                  cm.replaceRange('\n', {line: block_end+1, ch:0});
                }

                for (var i = block_start; i <= block_end; i++) {
                  cm.indentLine(i, 'subtract'); // TODO: this doesn't get tracked in the history, so can't be undone :(
                }
                cm.focus();
              } else {
                // insert code formatting
                var no_sel_and_starting_of_line = (cur_start.line === cur_end.line && cur_start.ch === cur_end.ch && cur_start.ch === 0);
                var sel_multi = cur_start.line !== cur_end.line;
                if (no_sel_and_starting_of_line || sel_multi) {
                  insertFencingAtSelection(cm, cur_start, cur_end, fenceCharsToInsert);
                } else {
                  _replaceSelection(cm, false, '`', '`');
                }
              }
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
                $(window).bind('hashchange', display_section); // handle back button
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

            $('.close', $help_area).bind('click', function() {
              $help_area.hide();
            });
        });
    }
});

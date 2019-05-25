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

var userMentionList;

var getProjectUsers = function(users_url) {
    $.get(users_url, function(data) {
        userMentionList = data.options.map(function(item) {
            return {
                text: item.value,
                displayText: item.label
            };
        });
    });
}

CodeMirror.registerHelper('hint', 'alluraUserMentions', function (editor) {
    var word = /[\w$]+/;
    var cur = editor.getCursor(), curLine = editor.getLine(cur.line);
    var tokenType = editor.getTokenTypeAt(cur);

    if(!!tokenType && tokenType.indexOf('comment') != -1) // Disable um inside code
        return;

    var end = cur.ch, start = end;
    while (start && word.test(curLine.charAt(start - 1))) --start;
    var curWord = start != end && curLine.slice(start, end);
    var list = [];
    if(curWord) {
        userMentionList.forEach(function(item) {
            if(item.displayText.indexOf(curWord) != -1)
                list.push(item);
        });
    }
    else {
        list = userMentionList.slice(); 
    }

    return { list: list, from: CodeMirror.Pos(cur.line, start), to: CodeMirror.Pos(cur.line, end) };
});
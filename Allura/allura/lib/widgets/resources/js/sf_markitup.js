$(window).load(function() {
    if(!window.markdown_init){
        window.markdown_init = true;
        $('textarea.sf_markdown_edit').markItUp(markdownSettings);
    }
});
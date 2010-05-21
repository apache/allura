$(document).ready(function(){
    var add_wiki_page_link = $('#sidebarmenu a.add_wiki_page');
    if(add_wiki_page_link.length){
        var add_page_form_holder = $('#create_wiki_page_holder');
        var make_page = function() {
		    location.href=add_wiki_page_link.attr('href')+$('input[name=name]', add_page_form_holder).val();
			add_page_win.dialog('close');
		};
        var add_page_win = add_page_form_holder.dialog({
    		autoOpen: false,
    		height: 150,
    		width: 400,
    		modal: true,
    		buttons: {
    			'Create page': make_page,
    			Cancel: function() {
    				$(this).dialog('close');
    			}
    		},
    		close: function() {
    			$('input[name=name]', add_page_form_holder).val('');
    		}
    	});
    	$('form', add_page_form_holder).submit(function(){
    	    make_page();
    	    return false;
    	});

        add_wiki_page_link.click(function(e){
		add_page_form_holder.dialog('open');
            return false;
        });
    }
});
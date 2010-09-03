(function() {
    $('form[action=set_custom_fields]').submit(function(evt) {
        $(this).find('input[name^=custom_fields-][name$=label]').each(function(){
            if(this.value==''){
                evt.preventDefault();
                flash('Every custom field must have a label', 'error');
            }
        });
        return true;
    });
}());

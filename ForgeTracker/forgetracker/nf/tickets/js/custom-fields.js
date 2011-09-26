(function() {
    $('form[action=set_custom_fields]').submit(function(evt) {
        $(this).find('input[name^=custom_fields-][name$=label]').each(function(){
            if(this.value==''){
                evt.preventDefault();
                flash('Every custom field must have a label', 'error');
            }
        });
        $(this).find('.state-field-container').each(function() {
            $(this)
                .filter(function() {
                    return $(this).find(':input:visible[name$=type]').val() == 'milestone';
                })
                .find(':input[name^=custom_fields-][name*=milestones-][name$=".name"]').each(function() {
                    if(this.value=='') {
                        evt.preventDefault();
                        flash('Every milestone must have a name', 'error');
                    }
                });
        });
        return true;
    });
}());

(function() {
    function add_field() {
        var $tpl = $('div.custom-field-stub');
        var $new_field = $tpl.clone(true);
        var num_flds = $('div.custom-field').length;
        $new_field.removeClass('ui-helper-hidden');
        $new_field.removeClass('custom-field-stub');
        $new_field.addClass('custom-field');
        $tpl.before($new_field);
        $new_field.find('select').change(show_hide_options).change();
        $new_field.find('input.delete').click(delete_field);
        $new_field.find('[name^=custom_fields#]').each(function(i) {
            var $this = $(this);
            var name = $this.attr('name');
            $this.attr('name', name.replace('#', '-' + (num_flds+1)));
            console.log('new name is', $this.attr('name'));
        });
        manage_messages();
    }

    function delete_field(){
        $(this).closest('div.custom-field').remove();
        manage_messages();
    }

    function show_hide_options(){
        var $this=$(this), show=$this.val()==='select';
        console.log('trying to hide', show);
        $this.closest('div.custom-field').find('div[data-name=options]').toggle(show)
    }

    function manage_messages(){
        if($('div.custom-field').length){
            $('#no_fields_message').hide();
            $('#has_fields_message').show();
        }
        else{
            $('#no_fields_message').show();
        $('#has_fields_message').hide();
        }
    }

    function validate(evt){
        $(this).find('div.custom-field input[name$=label]').each(function(ele){
            if(this.value==''){
                evt.preventDefault();
                flash('Every custom field must have a label', 'error');
            }
        });
        return true;
    }

    $(function(){
        $('#custom-field-list')
            .sortable()
            .closest('form')
            .submit(validate)
            .find('input.add')
            .click(add_field);
        var $flds = $('div.custom-field');
        $flds.find('select').change(show_hide_options).change();
        $flds.find('input.delete').click(delete_field);
        manage_messages();
    });
}());

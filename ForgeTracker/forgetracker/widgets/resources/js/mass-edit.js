$(function(){
    $('#id_search').val(window.location.search);
    $('#assigned_to').val('');
    $('#select_all').click(function(){
        if(this.checked){
            $('tbody.ticket-list input[type=checkbox]').attr('checked', 'checked');
        }
        else{
            $('tbody.ticket-list input[type=checkbox]').removeAttr('checked');
        }
    });
    $('#update-values').submit(function(){
        var $checked=$('tbody.ticket-list input:checked'), count=$checked.length;

        if ( !count ) {
            $('#result').text('No tickets selected for update.');
            return false;
        }

        $('#id_selected').val($checked.map(function(){ return this.name; }).get().join(','));
    });
});

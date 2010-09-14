var _gaq = _gaq || [];
$(document).ready(function() {
    var holder = $('#analytics');
    // Google
    _gaq.push(['_setAccount', 'UA-32013-6'], ['_trackPageview']);
    // Collective media
    $('<img src="//b.collective-media.net/seg/cm/cm_aa_gn1" width="1" height="1" alt=""/>')
        .appendTo(holder);
    // Quantcast
    _qoptions={qacct:"p-93nPV3-Eb4x22"};
    if(document.location.protocol=='https:') {
        // Google
        $('<script type="text/javascript" src="https://ssl.google-analytics.com/ga.js"></script>')
            .appendTo(holder);
        // Quantcast
        $('<script type="text/javascript" src="https://secure.quantserve.com/quant.js"></script>')
            .appendTo(holder);
        // comScore
        $('<script type="text/javascript" src="https://sb.scorecardresearch.com/beacon.js"></script>')
            .appendTo(holder);
    } else {
        // Google
        $('<script type="text/javascript" src="http://www.google-analytics.com/ga.js"></script>')
            .appendTo(holder);
        // Quantcast
        $('<script type="text/javascript" src="https://secure.quantserve.com/quant.js"></script>')
            .appendTo(holder);
        // comScore
        $('<script type="text/javascript" src="http://b.scorecardresearch.com/beacon.js"></script>')
            .appendTo(holder);
    }
    $('<script type="text/javascript">COMSCORE.beacon({'
      +'c1:2,c2:6035546,c3:"",c4:"",c5:"",c6:"",c15:""})</script>')
    .appendTo(holder);
});
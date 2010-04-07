a{
    color: ${color1};
    text-decoration: none;
}
a:visited, a:hover {color: ${color1};}
a:hover {text-decoration: underline;}


/* Top nav */

#mainmenu a:link, #mainmenu a:visited, #mainmenu a:active,
#nav_menu a:link, #nav_menu a:visited, #nav_menu a:active{
    text-decoration: none;
}
#mainmenu a:hover, #nav_menu a:hover{
    text-decoration: underline;
}
#mainmenu{
    border: 1px solid ${color2};
    border-width: 0 0 1px 0;
    height: 28px;
    padding-top: 8px;
}
#mainmenu .last a{
    float: right;
    margin-left: 2em;
}
#nav_menu_missing{
    height: 0;
    padding-top: 5px;
    border: 5px solid ${color2};
    border-width: 0 0 5px 0;
}
#nav_menu{
    background-color: ${color3};
    height: 62px;
    padding-top: 5px;
    color: #555;
    border: 5px solid ${color2};
    border-width: 0 0 5px 0;
}
#nav_menu .neighborhood_icon, #nav_menu .project_icon{
    width: 48px;
    height: 48px;
    display: block;
    margin: 5px;
}
#nav_menu .project_icon {
    margin:5px 0 0 15px;
}
#nav_menu .neighborhood{
    text-align: right;
}
#nav_menu .neighborhood_member{
    font-family: Georgia, serif;
}
#nav_menu a.neighborhood_name:link, #nav_menu a.neighborhood_name:visited, #nav_menu a.neighborhood_name:hover, #nav_menu a.neighborhood_name:active{
    color: #555;
    font-size: 1.3em;
    padding-top: 1.3em;
}
#nav_menu a.project_name:link, #nav_menu a.project_name:visited, #nav_menu a.project_name:hover, #nav_menu a.project_name:active{
    color: #000;
    font-size: 20px;
}
#nav_menu .project{
    position: relative;
    height: 62px;
}
#nav_menu ul.nav_links{
    position: absolute;
    bottom: 0;
    left: -3px;
    margin: 0;
    padding: 0;
}
#nav_menu ul.nav_links li{
    float: left;
    list-style-type: none;
}
#nav_menu ul.nav_links a:link,
#nav_menu ul.nav_links a:visited,
#nav_menu ul.nav_links a:hover,
#nav_menu ul.nav_links a:active{
    padding: 6px;
    color: #000;
    display: block;
    height: 15px;
}
#nav_menu ul.nav_links a:link.active,
#nav_menu ul.nav_links a:visited.active,
#nav_menu ul.nav_links a:hover.active,
#nav_menu ul.nav_links a:active.active{
    background-color: ${color2};
}
#nav_menu .home_icon{
    width: 10px;
    background-image: url(/images/home.png);
    background-repeat: no-repeat;
    background-position: center;
}


#content_holder{
    border-style: solid;
    border-color: ${color2};
    border-width: 0 0 1px 5px;
    width: 945px;
}
#content{
    border-style: solid;
    border-color: ${color4} ${color2} ${color4} ${color4};
    border-right-color: ${color2};
    border-width: 5px 1px 0 5px;
    width: 789px;
    min-height: 400px;
}
#content h1.title {
    background: ${color3};
    margin: -12px -12px 15px;
    font-size: 1.5em;
    padding: 10px 12px;
    border-bottom: 1px solid ${color4};
}
#content h2 {font-size: 1.3em;}

/* Side nav */
#app-search input{
	width: 125px;
	margin: 15px 11px 12px;
}
#sidebar
{
    margin-right: 0;
}
ul#sidebarmenu
{
    width: 100%;
    padding: 0;
}
ul#sidebarmenu li {
    list-style-type: none;
    margin: 0 0 0.3em;
    padding: 0;
}
ul#sidebarmenu li .nav_head{
    display: block;
    font-weight: bold;
    padding: 1em 1em 0;
}

ul#sidebarmenu li a {
    display:block;
    text-decoration: none;
    font-weight: normal;
    padding: 0 1em;
}
ul#sidebarmenu li a.active {
    background-color: ${color4};
}

ul#sidebarmenu li a.nav_child {
    padding-left:2em;
}
ul#sidebarmenu li a.nav_child2 {
    padding-left:4em;
}

ul#sidebarmenu span.ui-icon, ul#sidebarmenu a span.ui-icon,
#sidebar-right span.ui-icon, #sidebar-right a span.ui-icon,
.discussion-post span.ui-icon, .discussion-post a span.ui-icon,
.ui-button-set span.ui-icon, .ui-button-set a span.ui-icon{
    float: left;
    margin-right: 5px;
}

#sidebar-right
{
    position: relative;
    padding: 5px;
    background-color: ${color3};
    border-top: 5px solid ${color2}
}
#sidebar-right hr {
    margin: .2em 0;
    padding: 0;
    background: ${color4}
}

#footer{
	clear: both;
	margin: 1em 0;
}
#footer .foot_head{
    text-transform: uppercase;
    font-weight: bold;
}
#footer a:link, #footer a:visited, #footer a:hover, #footer a:active{
    color: #444;
    text-decoration: none;
}
#footer a:hover{
    text-decoration: underline;
}
#footer ul{
    margin: 0;
    padding: 0;
}
#footer li{
    list-style-type: none;
}

thead th {
    background-color: ${color2};
}
tbody .even{
    background-color: ${color3};
}

.defaultTextActive {
    color: #a1a1a1;
    font-style: italic;
}
.breadcrumbs
{
    height: 2em;
    width: 100%;
}

.breadcrumbs ul
{ 
    height: 2em;
    list-style-type: none;
    margin: 0;
    padding: 0;
}

.breadcrumbs ul li
{ 
    float: left;
    padding-left: 0.5em;
}

.breadcrumbs ul li:before
{	
    content: "\00BB";
}

.breadcrumbs ul li.first:before
{	
    content: "";
}

/* Collapsible boxes */

.title-pane .title
{
  background-color: ${color3};
  padding: 1px 6px;
  margin: 4px 1px 0 1px;
  border: 1px solid #333;
  font-weight:normal;
  font-size:12px;
  cursor: pointer;
}

.title-pane .title:before
{
    content: ' [-]  ';
}

.title-pane.closed .title:before
{
    content: ' [+] ';
}

.title-pane .content
{
    padding: .5em;
    border: 1px solid #ccc;
}

.title-pane.closed .content
{
    display:none;
}

/* Inline editing of content */
.editable.viewing .editor
{
    display: none;
}

.editable.editing .viewer
{
    display: none;
}

.editable .edit
{
    float:left;
    display:none;
}

.editable
{
    position: relative;
    margin-bottom: 5px;
}

.editable + .editable
{
    margin-top: 1em;
}

.editable:hover
{
    background-color: ${color2};
    cursor: pointer;
}

.editable:hover .edit
{
    float:left;
    position: absolute;
    top: -0.5em;
    display:block;
    border: 1px solid grey;
    background-color: #eee;
}

.forge_comment_body{
    margin-top: .5em;
    padding: .5em;
    border: 1px solid #ccc;
    overflow: auto;
}
.forge_comment_body .user_info{
    padding: .5em;
    border: 1px solid #ccc;
    float: right;
    text-align: center;

}}
.forge_comment_body .user_info img{
    margin: .5em;

}
.forge_comment_body .reply{
    clear: both;
}
.forge_comment_replies{
    margin-left: 1em;
}
.todo{
    background-color: #bebebe;
}
.attachment_images{
    overflow: auto;
}
.attachment_thumb{
    float: left;
    margin: .5em;
}
.tagEditor
{
	margin: 4px 0;
	padding: 0;
}

.tagEditor li
{
	display: inline;
	background-image: url(/images/minus_small.png);
	background-color: #eef;
	background-position: right center;
	background-repeat: no-repeat;
	list-style-type: none;
	padding: 0 18px 0 6px;
	margin: 0 4px;
	cursor: pointer;
	-moz-border-radius: 5px;
	-webkit-border-radius: 5px;
}

.tagEditor li:hover
{
	background-color: #eee;
}

#pyforge_directory{
    margin-top: 1em;
}
#pyforge_directory h3{
    margin: 1em 0 5px 0;
}
#pyforge_directory ul{
    padding-left: 1em;
    margin: 0;
}
#pyforge_directory li{
    list-style-type: none;
}
#pyforge_directory a:link, #pyforge_directory a:visited, #pyforge_directory a:active{
    text-decoration: none;
}
#pyforge_directory a:hover{
    text-decoration: underline;
}

input.title.wide.ticket_form_tags{
    width: 482px;
}

/* Wes fix */
	.span-3 label {display: block; text-align: right; vertical-align: middle;}
	input, textarea, .markItUpContainer, .markItUpPreviewFrame {border-color:${color2} !important;}
	input.title {font-size: 1em !important;}
	textarea {height: 100px;}
	.editable {padding: 2px;}
	.editable .viewer {padding: 4px 0;}
	.editor input, .editor textarea, .editor select {margin: 0;}
	thead th {border-bottom: 1px solid #94B1C7;}
	tr.even td {background-color: ${color3}}
	.closed {color: #b35959 }
	.open {color: #77b359;}
	.accepted {color: #576875;}
	/*#ticket-list tr > td:first-child, #ticket-list tr > th:first-child,*/
/*  .forums tr > th, .forums tr > td {text-align: center;}*/
	.forums tr .topic, .forums tr > th:last-child, .forums tr > td:last-child {text-align: left;}
	.forums tr .topic {width: 60%;}
	.forums {margin-bottom: 0;}
	#content .forums h3 {font-size: 1em; font-weight: bold; margin: 3px 0 .1em;}
	.forums tr .topic .ui-button {padding: 7px; margin: 3px 10px 4px 5px; border-width: thin !important;}
    #project-admin-overview .span-3 label {padding: 6px 0 11px;}
	.fakeinput {padding: .5em 2px;}
	.ui-tabs .ui-tabs-panel {padding: 1em .5em 0 0;}

	tr > th {color: ${color1};}
	tr > td {border-bottom: 1px solid ${color4};}
		.nav_links li {margin-right: .5em;}
		.gravatar img {border: 3px solid  ${color3}; margin-bottom: .2em; vertical-align: middle; -webkit-box-shadow: rgba(0, 0, 0, 0.5) 0px 0px 4px; -moz-box-shadow: rgba(0, 0, 0, 0.5) 0px 0px 4px;}
	.gravatar.sm img {border: 2px solid  ${color4}; margin: 0 .3em; vertical-align: middle; -webkit-box-shadow: none; -moz-box-shadow: none;}
	.gravatar {margin: 0 0 1em; display: block;}
	.gravatar.sm {margin: 0;}
	.tag {background-color: ${color2}; padding: .1em .4em;}
	.assoc, .date {color: #aaa; margin-bottom: 1em;}
	.hide {display: none;}
	#project-admin-overview hr {margin: .5em;}
	.arrow {background:none repeat scroll 0 0 #FFFFFF;
        color:${color2};
        font-size:15px;
        height:5px;
        left:112px;
        line-height:0;
        position:absolute;
        top:40px;}
    #newcomview, #newcomview2 {margin-top: -1em; margin-left: -3px;}
	#comment, #post {margin: -1em 0 2em; position: relative;}
	#comment textarea, #post textarea {width: 100%;}
	#comment input.title, #post input.title, input.title.wide {width: 100%;}
	.span-3 label {padding-top: 15px;}
	
	.ui-button:hover {text-decoration: underline !important;}
    .ui-state-default.ui-button { -webkit-box-shadow: rgba(0, 0, 0, 0.5) 0px 2px 4px; -moz-box-shadow: rgba(0, 0, 0, 0.5) 0px 2px 4px;}
    .ui-state-default.ui-button:hover {text-decoration: none !important; -webkit-box-shadow: rgba(0, 0, 0, 0.5) 0px 0px 2px; -moz-box-shadow: rgba(0, 0, 0, 0.5) 0px 0px 2px;}

    .icon {margin: .5em 1em .5em 0}

	select {margin: 10px 0; width: 100%;}
	.tcenter {text-align: center;}
	.tright {text-align: right;}
	.tleft {text-align: left;}
	.fleft {float: left; clear: left;}
	.fright {float: right; clear: right;}
    

	.error, .notice, .success {padding:.8em;margin-bottom:1em;border:2px solid #ddd;}
	.error {background:#FBE3E4;color:#8a1f11;border-color:#FBC2C4;}
	.notice {background:#FFF6BF;color:#514721;border-color:#FFD324;}
	.success {background:#E6EFC2;color:#264409;border-color:#C6D880;}
	.error a {color:#8a1f11;}
	.notice a {color:#514721;}
	.success a {color:#264409;}
	#forum-list .error {background:#8a1f11;}
	#forum-list .notice {background:#e5be20;}
	#forum-list .success {background:#264409;}
	
	.ui-accordion .ui-accordion-header a {
        padding-left: 2em;
    }

	a.ui-button {padding: .4em 1em .4em 1em; margin-right: .5em;}
	#sidebar-right hr {margin: .2em 0 !important; padding: 0; background: #D7E8F5;}
	#sidebar-right .span-2, #sidebar-right .span-3, #sidebar-right .span-4 {margin-bottom: .2em;}
	#sidebar-right small.badge {margin: 0 .5em 0 0;}

	.feed {margin-top: 1em; }
	.feed h3 {padding: .5em .8em; margin: 0 -10px 0 0; background: #e5e5e5; border-top: 1px solid #ddd;}
	.feed ul {margin: 0 -10px 0 0; background: #f5f5f5; padding: .5em 0; border-top: 4px solid #ddd;}
	.feed li {margin: 0 .4em .5em; padding: 0 .5em .5em; list-style: none; border-bottom: 1px solid #e5e5e5;}
	.feed li:last-child {border: none;}

	.feedc {margin-top: 1em; }
	.feedc h3 {padding: .5em .2em; margin: 0;}
	.feedc ul {margin: 0; padding: .5em 0; border-top: 4px solid #ddd;}
	.feedc li {margin: 0 0 .5em; padding: 0 .5em .5em; list-style: none; border-bottom: 1px solid #e5e5e5;}
	.feedc li:last-child {border: none;}

	.download {
		background: hsla(207,70%,30%, 1);
		background-image: -webkit-gradient(linear, 0% 0%, 0% 100%, from(hsla(207,70%,30%, 1)), to(hsla(207,70%,10%, 1)));
		background-image: -moz-linear-gradient(0% 100% 90deg,hsla(207,70%,10%, 1),hsla(207,70%,30%, 1));
		border-color: hsla(207,70%,10%, 1); 
		color: #fff !important;
		margin-bottom: -5px;
		width: 220px;
	}
	.download .ui-icon {background-image: url(/css/forge/images/ui-icons_ffffff_256x240.png); }

/* project_list styling */
    small.badge {	

    	background: ${color2};
    	color: ${color1};
    	padding: .1em .5em;
    	margin: 0;
    	-webkit-border-radius: 12px;
    	-moz-border-radius: 12px;
    	margin: 1em 1em .5em 0;
    	display: inline-table;
    	}

    small.badge:hover {	

    	background: #839CB0;
    	color: #fff;
    	padding: .1em .5em;
    	margin: 0;
    	margin: 1em 1em .5em 0;
    	display: inline-table;
    	}



    .tip {
    	display:none;
	background: #2C343B;
    	font-size:.85;
    	height:1.5em;
    	width:200px;
    	padding:.5em 1em;
    	color:#fff;	
    	-webkit-box-shadow: rgba(0, 0, 0, 0.5) 0px 2px 4px;
    	-moz-box-shadow: rgba(0, 0, 0, 0.5) 0px 2px 4px;
    	-webkit-border-radius: 4px;
    	-moz-border-radius: 4px;
    	border-radius: 4px;
    	text-align: center;
	border: 1px solid #111517;
    }

    #tippotm {	text-align: left; height:3em; padding-left: 55px; width: 130px; background-image: url('images/project-of-the-month-final.png'); background-position: 5px 50%; background-repeat: no-repeat;}

    #tipcca {	text-align: left; height:3em; padding-left: 55px; width: 190px; background-image: url('images/cca.png'); background-position: 5px 50%; background-repeat: no-repeat;}

    /* Not sure this is the best script - grid switching */
    #grid {position: relative;}
    ul.display {
    	float: left;
    	margin: 0;
    	padding: 0;
    	list-style: none;
    }
    ul.display li {
    	float: left;
    	padding: 10px 0;
    	margin: 0;
    	width: 100%;
    border-bottom: 1px solid #ddd;
    }
    ul.display li:last-child {border: none;}
    ul.display li a {
    	text-decoration: none;
    }
    ul.display li .content_block {
    	padding: 0 10px;
    }

    ul.display li p {margin-bottom: 0 !important;}

    ul.display li .content_block a img{
    	padding: 5px;
    	margin: 0 15px 0 0;
    	float: left;
    }

    ul.thumb_view li{
    	width: 240px;
    	margin-right: 15px;
    	height: 130px;
    	border: none;
    }

    ul.thumb_view li p{
    	margin: 10px 0 0 60px;
    }
    ul.thumb_view li .content_block a img {
    	margin: 0 0 10px;
    }

    ul.thumb_view li h2,
    ul.display li h2 {padding-top: 7px; margin-bottom: 0;}

    .switch {
    	position: absolute;
    	top: -50px;
    	right: 0;
    }
    .switch .ui-button,
    .switch .ui-button:hover { -webkit-box-shadow: none; -moz-box-shadow: none;}


    a:hover.switch_thumb {
    	filter:alpha(opacity=75);
    	opacity:.75;
    }


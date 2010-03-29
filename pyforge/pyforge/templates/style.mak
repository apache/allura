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

ul#sidebarmenu span.ui-icon, ul#sidebarmenu a span.ui-icon,
#sidebar-right span.ui-icon, #sidebar-right a span.ui-icon,
.discussion-post span.ui-icon, .discussion-post a span.ui-icon{
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
	#forum-list tr > th, #forum-list tr > td {text-align: center;}
	#forum-list tr > th:first-child, #forum-list tr > td:first-child, #forum-list tr > th:last-child, #forum-list tr > td:last-child {text-align: left;}
	#forum-list tr > th:first-child, #forum-list tr > td:first-child {width: 50%;}
	#forum-list h2 {font-size: 1em; font-weight: bold; margin: 0 0 .1em;}
	#forum-list tr > td:first-child .ui-button {padding: 7px 2px 7px 7px; margin: 3px 10px 4px 5px; border-width: thin !important;}
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
	#comment, #post {margin: -1em 0 2em; position: relative;}
	#comment textarea, #post textarea {width: 100%;}
	#comment input.title, #post input.title, input.title.wide {width: 100%;}
	.span-3 label {padding-top: 15px;}

    .ui-button { -webkit-box-shadow: rgba(0, 0, 0, 0.3) 0px 2px 3px; -moz-box-shadow: rgba(0, 0, 0, 0.3) 0px 2px 3px;}
    .ui-button:hover { -webkit-box-shadow: rgba(0, 0, 0, 0.5) 0px 0px 2px; -moz-box-shadow: rgba(0, 0, 0, 0.5) 0px 0px 2px;}
    a.ui-button {padding: .4em 1em .4em .4em; margin-right: .5em;}

	select {margin: 15px 0; width: 100%;}
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
from allura.model import Neighborhood
from ming.orm import ThreadLocalORMSession


homepage = """<style type="text/css">
ul.ui-tab { display: none; }
div.content {
    font-family: Helvetica;
}
div.content div.row > div.column {
    width: 100%
}
div.welcome { margin: 2em 0; }
div.welcome p {
    display: block;
    position: relative;
    left: 8em;
    width: 80%;
}
div.welcome a {
    display: inline-block;
    font-weight: 600;
    color: white;
    margin-left: 1.5em;
    padding: 0.5em 1.5em 0.45em 1.5em;
    text-decoration: none;
    -webkit-border-radius: 5px;
    -moz-border-radius: 5px;
	background: rgb(0,0,0);
		background-image: -webkit-gradient(linear, 0% 0%, 0% 100%, to(rgb(0,0,0)), from(rgb(90,90,90)));
		background-image: -moz-linear-gradient(100% 100% 90deg, rgb(0,0,0), rgb(90,90,90) 100%);
    border: 1px solid black;
}
div.inner-row { 
    display: block;
    position: relative;
    padding: 1em 1em 1em 10em;
}
div.inner-row + div.inner-row { padding-top: 4.8em; }
div.tool {
    display: inline-block;
    position: relative;
    width: 30%;
    padding: 0 1em 3em 0;
}
div.tool img {
    position: absolute;
    left: -64px;
    top: 0;
}
div.tool h1, div.welcome {
    font-size:18px;
    font-weight: 300;
}
div.tool h1 {
    position: relative;
    top: -10px;
}
div.tool p {
    display: block;
    font-size: 13px;
    line-height: 18px;
    position: absolute;
    padding-right: 6em;
    top: 12px;
}
</style>
<div class="welcome">
    <p>We provide the tools.  You create great open source software.
    <a href="/p/add_project">Start&nbsp;Your&nbsp;Project</a>
    </p>
</div>
<div class="inner-row">
    <div class="tool">
        <img src="/nf/allura/images/wiki_48.png">
        <h1>Wikis</h1>
        <p>
            Documentation is key to your project and the wiki tool helps make it easy for anyone to contribute.
        </p>
    </div>
    <div class="tool">
        <img src="/nf/allura/images/code_48.png">
        <h1>Code</h1>
        <p>
            SVN, Git and Mercurial will help you keep track of your changes.
        </p>
    </div>
    <div class="tool">
        <img src="/nf/allura/images/tickets_48.png">
        <h1>Tickets</h1>
        <p>
            Bugs, enhancements, tasks, etc., will help you plan and manage your development.
        </p>
    </div>
</div>
<div class="inner-row">
    <div class="tool">
        <img src="/nf/allura/images/downloads_48.png">
        <h1>Downloads</h1>
        <p>
            Use the largest free, managed, global mirror network to distribute your files.
        </p>
    </div>
    <div class="tool">
        <img src="/nf/allura/images/stats_48.png">
        <h1>Stats</h1>
        <p>
            Follow the download trends that enable you to develop better software.
        </p>
    </div>
    <div class="tool">
        <img src="/nf/allura/images/forums_48.png">
        <h1>Forums</h1>
        <p>
            Collaborate with your community in your forums.
        </p>
    </div>
</div>
"""

projects_neighborhood = Neighborhood.query.find(dict(name='Projects')).first()
projects_neighborhood.homepage = homepage
ThreadLocalORMSession.flush_all()

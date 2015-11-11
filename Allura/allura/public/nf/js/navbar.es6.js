'use strict';

/**
 * Gets the current project url.

 * @constructor
 * @param {bool} rest - Return a "rest" version of the url.
 * @returns {string}
 */
function _getProjectUrl(rest = true) {
    var nbhd, proj, nbhd_proj;
    var ident_classes = document.getElementById('page-body').className.split(' ');
    for (var cls of ident_classes) {
        if (cls.indexOf('project-') === 0) {
            proj = cls.slice('project-'.length);
        }
    }
    nbhd = window.location.pathname.split('/')[1];
    if (proj === '--init--') {
        nbhd_proj = nbhd;
    } else {
        nbhd_proj = `${nbhd}/${proj}`;
    }
    return (rest ? '/rest/' : '/') + nbhd_proj;
}

function slugify(text) {
    return text.toString().toLowerCase()
        .replace(/\s+/g,/\s+/g,/\s+/g,/\s+/g, '-')           // Replace spaces with -
        .replace(/[^\w\-]+/g,/[^\w\-]+/g,/[^\w\-]+/g,/[^\w\-]+/g, '')       // Remove all non-word chars
        .replace(/\-\-+/g,/\-\-+/g,/\-\-+/g,/\-\-+/g, '-')         // Replace multiple - with single -
        .replace(/^-+/,/^-+/,/^-+/,/^-+/, '')             // Trim - from start of text
        .replace(/-+$/,/-+$/,/-+$/,/-+$/, '');            // Trim - from end of text
}
/**
 * Get the color for a tool type

 * @constructor
 * @label string 'The default mount label for a tool.  i.e. git and hg use 'Code' which returns 'blue'.
 * @return {string}
 */

function _getToolColor(defaultLabel='standard') {
    // Replace with css... (if we even want to keep the color)
    switch (defaultLabel) {
    case 'Wiki':
        return '#DDFFF0';
    case 'Git':  // Git, svn, hg
        return '#BBDEFB';
    case 'Mercurial':  // Git, svn, hg
        return '#BBDEFB';
    case 'Tickets':
        return '#D1C4E9';
    case 'Discussion':
        return '#DCEDC8';
    case 'Blog':
        return '#FFF9C4';
    case 'Link':
        return '#FFCDD2';
    default:
        return 'white';
    }
}
/**
 * Get a mount point from a NavBarItem node.

 * @constructor
 * @param {NavBarItem} node
 * @returns {string}
 */
function getMountPoint(node) {
    if(node.hasOwnProperty('mount_point') && node['mount_point'] !== null){
        return node['mount_point'];
    }
    return node.props.children[0].props.mount_point;
}

/**
 * Get a url from a NavBarItem node.

 * @constructor
 * @param {NavBarItem} node
 * @returns {string}
 */
function getUrlByNode(node) {
    if(node.hasOwnProperty('url') && node['url'] !== null){
        return node['url'];
    }
    return node.props.children[0].props.url;
}

function ToolsPropType() {
    return {
        name: React.PropTypes.string.isRequired,
        url: React.PropTypes.string.isRequired,
        isSubmenu: React.PropTypes.bool,
        tools: React.PropTypes.arrayOf(
            React.PropTypes.shape({
                ordinal: React.PropTypes.number,
                mount_point: React.PropTypes.string,
                name: React.PropTypes.string,
                url: React.PropTypes.string,
                is_anchored: React.PropTypes.bool,
                tool_name: React.PropTypes.string,
                icon: React.PropTypes.string
            })
        ).isRequired
    };
}

/**
 * A single NavBar item.

 * @constructor
 */
var NavBarItem = React.createClass({
    propTypes: {
        name: React.PropTypes.string.isRequired,
        url: React.PropTypes.string.isRequired
    },

    isAnchored: function() {
        return this.props.is_anchored !== null;
    },

    render: function() {
        var handle = this.props.handleType.slice(1);
        var _base = handle + " ordinal-item";
        var spanClasses = this.props.isGrouper ? _base += " toolbar-grouper": _base;
        var classes = this.props.is_anchored ? "anchored " : handle;

        return (
            <div className={classes + " tb-item tb-item-edit ordinal-item"}>
                <a>
                    {!this.props.isGrouper && <i className='config-tool fa fa-cog'></i>}
                    <span
                        className={spanClasses}
                        data-mount-point={this.props.mount_point}>
                        {this.props.name}
                    </span>
                </a>
            </div>
        );
    }
});



/**
 * An input component that updates the NavBar's grouping threshold.

 * @constructor
 */
var GroupingThreshold = React.createClass({
    propTypes: {
        initialValue: React.PropTypes.number.isRequired
    },
    getInitialState: function() {
        return {
            value: this.props.initialValue
        };
    },

    handleChange: function(event) {
        this.setState({
            value: event.target.value
        });
        this.props.onUpdateThreshold(event);
    },

    render: function() {
        return (
            <div>
                { !!this.props.isHidden &&
                <div id='threshold-config'>
            <span>
              <label htmlFor='threshold-input'>Grouping Threshold</label>
                <input type='number' name='threshold-input' className='tooltip'
                       title='Number of tools allowed before grouping.'
                       value={ this.state.value }
                       onChange={ this.handleChange }
                       min='1' max='10'/>
              </span>
                </div> }
            </div>
        );
    }
});

/**
 * The NavBar when in "Normal" mode.

 * @constructor
 */
var NormalNavItem = React.createClass({
  mixins: [React.addons.PureRenderMixin],

    render: function() {

        return (
            <li  key={`tb-norm-${_.uniqueId()}`}>
                <a href={ this.props.url } className={ this.props.classes }>
                    { this.props.name }
                </a>
                {this.props.children}
            </li>
        );
    }
});

/**
 * Toggle Button

 * @constructor
 */
var ToggleAddNewTool = React.createClass({
    getInitialState: function() {
        return {
            visible: false
        };
    },
    handleToggle: function() {
        this.setState({
            visible: !this.state.visible
        });
    },
    render: function() {
        return <AddNewToolButton showAddToolMenu={this.state.visible}
                                 handleToggleAddNewTool={this.handleToggle} />;
    }
});

/**
 * The NavBar when in "Normal" mode.

 * @constructor
 */
var NormalNavBar = React.createClass({
    buildMenu: function(item, i) {
        let classes = window.location.pathname.startsWith(item.url) ? 'active-nav-link' : '';

        var subMenu;
        if (item.children) {
            subMenu = item.children.map(this.buildMenu);
        }
        return (
            <NormalNavItem url={item.url} name={item.name} classes={classes} key={`normal-nav-${_.uniqueId()}`}>
                <ul>
                    {subMenu}
                </ul>
            </NormalNavItem>
        );
    },

    render: function() {
        var listItems = this.props.items.map(this.buildMenu);
        return (
            <ul
                id="normal-nav-bar"
                className="dropdown">
                { listItems }
                <li><ToggleAddNewTool/></li>
            </ul>
        );
    }
});

/**
 * The NavBar when in "Admin" mode.
 * @constructor
 */
var AdminNav = React.createClass({
    propTypes: {
        tools: React.PropTypes.arrayOf(
            React.PropTypes.objectOf(ToolsPropType))
    },
    mode: 'grid',
    getInitialState: function() {
        return {
            hover: false
        };
    },

    mouseOver: function() {
        this.setState({
            hover: true
        });
    },

    mouseOut: function() {
        this.setState({
            hover: false
        });
    },

    buildMenu: function (items, isSubMenu=false) {
        var _this = this;
        var [tools, anchored_tools, end_tools] = [[], [], []];

        for (let item of items) {
            var subMenu;
            if (item.children) {
                subMenu = this.buildMenu(item.children, true);
            }

            var _handle = isSubMenu ? ".draggable-handle-sub" : '.draggable-handle';

            var core_item = <NavBarItem
                {..._this.props}
                mount_point={ item.mount_point }
                name={ item.name }
                handleType={_handle}
                isGrouper={item.children && item.children.length > 0}
                url={ item.url }
                key={ 'tb-item-' + _.uniqueId() }
                is_anchored={ item.is_anchored || item.mount_point === 'admin'}/>;
            if (item.mount_point === 'admin') {
                // force admin to end, just like 'Project.sitemap()' does
                end_tools.push(core_item);
            } else if (item.is_anchored) {
                anchored_tools.push(core_item);
            } else {
                tools.push(<DraggableTool key={_.uniqueId()} tool={core_item} subMenu={subMenu} />
                );
            }
        }

        return (
        <div className='react-drag'>
                { anchored_tools }
                <ReactReorderable
                    key={ 'reorder-' + _.uniqueId() }
                    handle={_handle}
                    mode='grid'
                    onDrop={ _this.props.onToolReorder }>
                    { tools }
                </ReactReorderable>
                { end_tools }
            </div>
        );
    },

    render: function () {
        var tools = this.buildMenu(this.props.tools);
        return <div>{tools}</div>;
    }
});

/**
 * A wrapper for non-anchored tools
 * @constructor
 */
var DraggableTool = React.createClass({
    render: function () {
        return (
            <div className={" draggable-element "}>
                { this.props.tool }
                {this.props.subMenu &&
                <AdminItemGroup key={_.uniqueId()}>
                    {this.props.subMenu}
                </AdminItemGroup>
                    }
            </div>
        );
    }
});


/**
 * The NavBar when in "Admin" mode.
 * @constructor
 */
var AdminItemGroup = React.createClass({
    render: function () {
        return (
            <div className="tb-item-grouper">
                {this.props.children}
            </div>
        );
    }
});

/**
 * The button that toggles NavBar modes.

 * @constructor
 */
var ToggleAdminButton = React.createClass({
    propTypes: {
        visible: React.PropTypes.bool
    },
    render: function() {
        var classes = this.props.visible ? 'fa fa-unlock' : 'fa fa-lock';
        return (
            <button id='toggle-admin-btn' onClick={ this.props.handleButtonPush } className='admin-toolbar-right'>
                <i className={ classes }></i>
            </button>
        );
    }
});

/**
 * The main "controller view" of the NavBar.

 * @constructor
 * @param {object} initialData - Consumes the _nav.json endpoint.
 */
var Main = React.createClass({
    propTypes: {
        initialData: React.PropTypes.objectOf(ToolsPropType),
        installableTools: React.PropTypes.array
    },
    getInitialState: function() {
        return {
            data: this.props.initialData,
            visible: true,
            _session_id: $.cookie('_session_id')
        };
    },

    /**
     * When invoked, this updates the state with the latest data from the server.
     */
    getNavJson: function() {
        $.get(`${_getProjectUrl(false)}/_nav.json`, function(result) {
            if (this.isMounted()) {
                this.setState({
                    data: result
                });
            }
        }.bind(this));
    },
    /**
     * Handles the locking and unlocking of the NavBar
     */
    handleToggleAdmin: function() {
        this.setState({
            visible: !this.state.visible
        });
    },

    /**
     * Handles the changing of the NavBars grouping threshold.

     * @param {object} event
     */
    onUpdateThreshold: function(event) {
        var _this = this;
        var thres = event.target.value;
        var url = `${_getProjectUrl()}/admin/configure_tool_grouping`;
        var csrf = $.cookie('_session_id');
        var data = {
            _session_id: csrf,
            grouping_threshold: thres
        };
        var _data = this.state.data;
        _data.grouping_threshold = thres;
        this.setState({
            data: _data
        });
        this.setState({
            in_progress: true
        });
        $.post(url, data, function() {
        }.bind(this)).always(function() {
            _this.setState({
                in_progress: false
            });
        });

        _this.getNavJson();
        return false;
    },



    /**
     * Handles the sending and updating tool ordinals.

     * @param {array} data - Array of tools
     */
    onToolReorder: function() {
        var params = {_session_id: $.cookie('_session_id')};
        var toolNodes = $("#top_nav_admin").find('span.ordinal-item').not(".toolbar-grouper");
        for (var i = 0; i < toolNodes.length; i++) {
            params[i] = toolNodes[i].dataset.mountPoint;
        }

        var _this = this;
        var url = _getProjectUrl() + '/admin/mount_order';
        $.ajax({
            type: 'POST',
            url: url,
            data: params,
            success: function () {
                $('#messages').notify('Tool order updated',
                    {
                        status: 'confirm',
                        interval: 500,
                        timer: 2000
                    });
                _this.getNavJson();
            },

            error: function() {
                $('#messages').notify('Error saving tool order.',
                    {
                        status: 'error'
                    });
            }
        });
    },

    render: function() {
        var _this = this;
        var navBarSwitch = (showAdmin) => {
            if (showAdmin) {
                return (
                    <AdminNav
                        tools={ _this.state.data.menu }
                        data={ _this.state.data }
                        onToolReorder={ _this.onToolReorder }
                        editMode={ _this.state.visible } />
                );
            } else {
                return (
                    <div>
                        <NormalNavBar
                            items={ _this.state.data.menu }
                            />
                    </div>
                );
            }
        };
        var navBar = navBarSwitch(this.state.visible);

        return (
            <div
                className={ 'nav_admin '}>
                { navBar }
                <div id='bar-config'>
                    <GroupingThreshold
                        onUpdateThreshold={ this.onUpdateThreshold }
                        isHidden={ this.state.visible }
                        initialValue={ this.state.data.grouping_threshold }/>
                </div>
                <ToggleAdminButton
                    handleButtonPush={ this.handleToggleAdmin }
                    visible={ this.state.visible }/>
            </div>
        );
    }
});

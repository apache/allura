'use strict';

/**
 * Gets the current url.

 * @constructor
 * @param {bool} rest - Return a "rest" version of the url.
 * @returns {string}
 */
function _getProjectUrl(rest = true) {
    var [nbhd, proj] = window.location.pathname.split('/').slice(1, 3);
    var base = `${window.location.protocol}//${window.location.host}`;
    return rest ? `${base}/rest/${nbhd}/${proj}` : `${base}/${nbhd}/${proj}`;
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
    return node.props.children.props.children.props.mount_point;
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
        url: React.PropTypes.string.isRequired,
    },

    isAnchored: function() {
        return this.props.is_anchored !== null;
    },

    render: function() {
        var controls = [<i className='config-tool fa fa-cog'></i>];
        var arrow_classes = 'fa fa-arrows-h';
        if (this.props.is_anchored) {
            arrow_classes += ' anchored';
        } else {
            arrow_classes += ' draggable-handle';
        }
//controls.push(<i className={arrow_classes}></i>);
        return (
            <div className="tb-item tb-item-edit">
                <a>{controls}
                    <span className="draggable-handle">{this.props.name}</span></a>
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
var NormalNavBar = React.createClass({
    buildMenu: function(item) {
        let classes = window.location.pathname.startsWith(item.url) ? 'active-nav-link' : '';

        var subMenu;
        if (item.children) {
            subMenu = item.children.map(this.buildMenu);
        }

        return (
            <li>
                <a href={ item.url } key={ 'link-' + _.uniqueId() } className={ classes }>
                    { item.name }
                </a>
                {subMenu &&
                    <ul className={ classes + ' submenu'}>
                        { subMenu }
                    </ul>
                }
            </li>
        );
    },

    render: function() {
        var listItems = this.props.items.map(this.buildMenu);
        var classes = 'dropdown';
        return (
            <ul
                id="admin-toolbar-list"
                className={ classes }
                key={ `toolList-${_.uniqueId()}` }>
                { listItems }
                <ToggleAddNewTool
                    handleToggleAddNewTool={this.props.handleToggleAddNewTool}
                    showAddToolMenu={this.props.showAddToolMenu} />
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
        isSubmenu: React.PropTypes.bool,
        tools: ToolsPropType
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

    render: function() {
        var _this = this;
        var subMenuClass = this.props.isSubmenu ? ' submenu ' : '';
        var [tools, anchored_tools, end_tools] = [[], [], [],];
        this.props.tools.forEach(function(item) {
            var core_item = <NavBarItem
                                onMouseOver={ _this.mouseOver }
                                onMouseOut={ _this.mouseOut } {..._this.props}
                                data={ item }
                                mount_point={ item.mount_point }
                                name={ item.name }
                                url={ item.url }
                                key={ 'tb-item-' + _.uniqueId() }
                                is_anchored={ item.is_anchored || item.mount_point === 'admin'}/>;
            if (item.mount_point === 'admin') {
                // force admin to end, just like 'Project.sitemap()' does
                end_tools.push(core_item);
            } else if (item.is_anchored) {
                anchored_tools.push(core_item);
            } else {
                tools.push(
                    <div className={ 'draggable-element' + subMenuClass } key={ 'draggable-' + _.uniqueId() }>
                        { core_item }
                    </div>
            );
            }
        });

        return (
            <div className='react-drag edit-mode'>
                { anchored_tools }
                <ReactReorderable
                    key={ 'reorder-' + _.uniqueId() }
                    handle='.draggable-handle'
                    mode='grid'
                    onDragStart={ this.onDragStart }
                    onDrop={ this.props.onToolReorder }
                    onChange={ this.onChange }>
                    { tools }
                </ReactReorderable>
                { end_tools }
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
        initialData: ToolsPropType,
        installableTools: React.PropTypes.array
    },
    getInitialState: function() {
        return {
            data: this.props.initialData,
            visible: false,
            showAddToolMenu: false,
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
     * Handles the the display of the "Add new tool" menu.
     */
    handleToggleAddNewTool: function() {
        $('body').click(function(e) { // click the background
                if (e.target == this) {
                    $(this).fadeOut();
                }
            });

        this.setState({
            showAddToolMenu: !this.state.showAddToolMenu
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
     * Handles the changing of the NavBars grouping threshold.

     * @param {array} data - Array of tools
     */
    onToolReorder: function(data) {
        var tools = this.state.data;
        var params = {
            _session_id: $.cookie('_session_id')
        };

        data.map(function(tool, i) {
            var mount_point = getMountPoint(tool);
            var index = tools.children.findIndex(
                x => x.mount_point === mount_point
            );
            tools.children[index].ordinal = i;
            params[i] = mount_point;
        });

        this.setState({
            data: tools
        });
        var _this = this;
        var url = _getProjectUrl() + '/admin/mount_order';
        $.ajax({
            type: 'POST',
            url: url,
            data: params,
            success: function() {
                $('#messages').notify('Tool order updated',
                    {
                        status: 'confirm'
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
        var editMode = this.state.visible ? 'edit-mode' : '';
        var _this = this;
        var navBarSwitch = (showAdmin) => {
            if (showAdmin) {
                return (
                    <AdminNav
                        tools={ _this.state.data.menu }
                        data={ _this.state.data }
                        onToolReorder={ _this.onToolReorder }
                        onUpdateMountOrder={ _this.onUpdateMountOrder }
                        editMode={ _this.state.visible } />
                );
            } else {
                return (
                    <div>
                        <NormalNavBar
                            items={ _this.state.data.menu }
                            handleToggleAddNewTool={this.handleToggleAddNewTool}
                            showAddToolMenu={this.state.showAddToolMenu}/>
                    </div>
                );
            }
        };
        var navBar = navBarSwitch(this.state.visible);

        return (
            <div
                ref={ _.uniqueId() }
                className={ 'nav_admin ' + editMode }>
                { navBar }
                <div id='bar-config'>
                    <GroupingThreshold
                        onUpdateThreshold={ this.onUpdateThreshold }
                        isHidden={ this.state.visible }
                        initialValue={ this.state.data.grouping_threshold }/>
                </div>
                <ToggleAdminButton
                    key={ _.uniqueId() }
                    handleButtonPush={ this.handleToggleAdmin }
                    visible={ this.state.visible }/>
            </div>
        );
    }
});

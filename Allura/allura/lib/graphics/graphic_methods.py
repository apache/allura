import StringIO

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import Image


def create_histogram(data, tick_labels, y_label, title):
    fig = Figure(figsize=(10,5), dpi=80, facecolor='white')
    ax = fig.add_subplot(111, axisbg='#EEEEFF')

    canvas = FigureCanvasAgg(fig)
    n, bins, patches = ax.hist(data, facecolor='#330099', edgecolor='white')
    ax.set_ylabel(y_label)
    ax.set_title(title)

    ax.set_xticks(range(len(tick_labels)+1))
    ax.get_xaxis().set_ticklabels(tick_labels, rotation=45, va='top', ha='right')
    ax.get_xaxis().set_ticks_position('none')
    ax.set_autoscalex_on(False)

    ax.set_xlim((-1, len(tick_labels)))
    ax.set_ylim((0, 1+max([data.count(el) for el in data])))
    fig.subplots_adjust(bottom=0.3)

    canvas.draw()

    s = canvas.tostring_rgb()
    l,b,w,h = fig.bbox.bounds
    w, h = int(w), int(h)

    output = StringIO.StringIO()
    im = Image.fromstring( "RGB", (w,h), s)
    im.save(output, 'PNG')

    return output.getvalue()

def create_progress_bar(value):
    value = value / 100.0
    if value < 1 / 5.0:
        color = 'red'
    elif value < 2 / 5.0:
        color = 'orange'
    elif value < 3 / 5.0:
        color = 'yellow'
    elif value < 4 / 5.0:
        color = 'lightgreen'
    else:
        color = 'green'

    fig = Figure(figsize=(3,0.5), dpi=40, facecolor='gray')
    canvas = FigureCanvasAgg(fig)
    canvas.draw()

    from matplotlib.patches import Rectangle
    from matplotlib.axes import Axes

    fig.draw_artist(Rectangle((0,0), int(value * 120), 20, color=color))
    fig.draw_artist(Rectangle((1,0), 119, 19, fill=False, ec='black'))

    l,b,w,h = fig.bbox.bounds
    s = canvas.tostring_rgb()
    w, h = int(w), int(h)

    output = StringIO.StringIO()
    im = Image.fromstring( "RGB", (w,h), s)
    im.save(output, 'PNG')

    return output.getvalue()

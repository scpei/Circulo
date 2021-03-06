# Goal is to annotate a vertex cover with dictionary representing various cluster metrics
from igraph import Cover, VertexCover
from scipy import nansum, nanmax
from scipy.sparse import dok_matrix
import uuid
import collections
import time
from circulo.metrics.omega import omega_index
from circulo.utils.general import aggregate
import circulo.metrics.graph
import numpy as np

def __get_weight_attr(G, metric_name, weights):
    '''
    :G graph
    :metric_name the name of the metric calling this function
    :weights

    return (weight_attr, remove) where weight_attr is the weight attribute name, and "remove" is a boolean
        as to wether to get rid of the weight attribute. This happens if we create the weight attribute for
        the purpose of the metric

    '''

    #if the weights parameter is a string then the graph utilizes weights
    if isinstance(weights, str):
      return (weights, False)
    #if the weights is being used for something else, then we
    elif weights is not None:
      attr_name = uuid.uuid5(uuid.NAMESPACE_DNS, '{}.circulo.lab41'.format(metric_name))
      G.es[attr_name] = weights
      return (attr_name, True)
    return (None, False)

def __remove_weight_attr(G, attr_name, remove):
    if remove:
      del G.es[uid]

def __weighted_sum(external_edges, w_attr):
  return len(external_edges) if w_attr is None else sum([ e[w_attr] for e in external_edges ])

def fomd(cover, weights=None):
    '''
    Fraction over median (weighted) degree is the number of nodes that have an internal (weighted) degree greater than the median (weighted) degree of
    all nodes in the graph.
    '''
    w_attr, remove = __get_weight_attr(cover.graph, 'fomd', weights)

    import scipy
    median = scipy.median(cover.graph.strength(weights=w_attr))
    rv = []
    for subgraph in cover.subgraphs():
        rv += [sum(1.0 for v in subgraph.strength(weights=w_attr) if v > median)/subgraph.vcount()]

    __remove_weight_attr(cover.graph, w_attr, remove)
    return rv

def expansion(cover, weights=None):
    '''
    Expansion is the ratio between the (weighted) number of external (boundary) edges in a cluster and the number of nodes in the cluster.

    :return list of expansion values, one for each community
    '''
    w_attr, remove = __get_weight_attr(cover.graph, 'expansion', weights)
    rv = []
    external_edges = cover.external_edges()
    for i in range(len(cover)):
        size_i = cover.size(i)
        rv += [1.0*__weighted_sum(external_edges[i], w_attr)/size_i]

    __remove_weight_attr(cover.graph, w_attr, remove)
    return rv

def cut_ratio(cover, allow_nan=False):
    '''
    Cut ratio is the ratio between the number of external (boundary) edges in a cluster and the cluster's maximum possible number of external edges

    Args:
        allow_nan:
    '''

    mode = "nan" if allow_nan == True else 0
    rv = []
    external_edges = cover.external_edges()

    size_g = cover.graph.vcount()
    for i in range(len(cover)):
        size_i = cover.size(i)
        denominator = (size_i*(size_g-size_i))
        rv += [1.0*len(external_edges[i])/denominator if denominator > 0 else float(mode)]
    return rv

def conductance(cover, weights=None, allow_nan=False):
    '''
    Conductance is the ratio between the (weighted) number of external (boundary) edges in a cluster and the cluster's total (weighted) number of edges
    '''
    w_attr, remove = __get_weight_attr(cover.graph, 'conductance', weights)

    mode = "nan" if allow_nan else 0
    rv = []
    external_edges = cover.external_edges()
    for i in range(len(cover)):
        int_edges_cnt = __weighted_sum(cover.subgraph(i).es(), w_attr)
        ext_edges_cnt = __weighted_sum(external_edges[i], w_attr)
        denominator = (2.0*int_edges_cnt+ext_edges_cnt)

        rv += [ext_edges_cnt/denominator if denominator > 0 else float(mode)]


    __remove_weight_attr(cover.graph, w_attr, remove)
    return rv

def separability(cover, weights=None, allow_nan = False):
    '''
    Separability is the ratio between the (weighted) number of internal edges in a cluster and its (weighted) number of external (boundary) edges.
    '''

    mode = "nan" if allow_nan else 0
    w_attr, remove = __get_weight_attr(cover.graph, 'separability', weights)
    rv = []
    external_edges = cover.external_edges()
    for i in range(len(cover)):
        int_edges_cnt = __weighted_sum(cover.subgraph(i).es(), w_attr)
        ext_edges_cnt = __weighted_sum(external_edges[i], w_attr)
        rv += [1.0*int_edges_cnt/ext_edges_cnt if ext_edges_cnt > 0 else float(mode)]

    __remove_weight_attr(cover.graph, w_attr, remove)
    return rv


def normalized_cut(cover, weights=None, allow_nan = False):
    '''
    Normalized cut is the sum of (weighted) conductance with the fraction of the (weighted) number of external edges over (weighted) number of all non-cluster edges
    '''
    w_attr, remove = __get_weight_attr(cover.graph, 'normalized_cut', weights)
    mode = "nan" if allow_nan else 0

    rv = cover.conductance(weights)
    external_edges = cover.external_edges()
    for i in range(len(cover)):
        int_edges_cnt = __weighted_sum(cover.subgraph(i).es(), w_attr)
        ext_edges_cnt = __weighted_sum(external_edges[i], w_attr)
        tot_edge_cnt = __weighted_sum(cover.graph.es(), w_attr)
        denominator = (2.0*(tot_edge_cnt - int_edges_cnt)+ext_edges_cnt)
        rv[i] += ext_edges_cnt/denominator if denominator > 0 else float(allow_nan)

    __remove_weight_attr(cover.graph, w_attr, remove)
    return rv

def maximum_out_degree_fraction(cover, odf=None, weights=None):
    '''
    Out Degree Fraction (ODF) of a node in a cluster is the ratio between its number of external (boundary) edges
    and its internal edges. Maximum ODF returns the maximum fraction for the cluster.
    '''
    if odf is None:
        odf = out_degree_fraction(cover, weights)
        odf = odf.tocsc()

    rv = []
    max_seen = odf.max(0).tocsc()
    for i in range(len(cover)):
        rv.append(max_seen[0,i])
    return rv #[ nanmax(ratios) for ratios in odf ]

def average_out_degree_fraction(cover, odf=None, weights=None):
    '''
    Out Degree Fraction (ODF) of a node in a cluster is the ratio between its number of external (boundary) edges
    and its internal edges. Average ODF returns the average fraction for the cluster.
    '''
    rv = []
    if odf is None:
        odf = out_degree_fraction(cover, weights)
        odf.tocsc()

    sums = odf.sum(0)
    for i in range(len(cover)):
      rv += [ sums[0,i]/cover.subgraph(i).vcount() ]
    return rv

def flake_out_degree_fraction(cover, odf=None, weights=None):
    '''
    Out Degree Fraction (ODF) of a node in a cluster is the ratio between its number of external (boundary) edges
    and its internal edges. Flake ODF returns the number of nodes for which this ratio is less than 1, i.e. a node has fewer internal edges than external ones.
    '''
    rv = []
    if odf is None:
        odf = out_degree_fraction(cover, weights)
        odf = odf.tocsc()

    for i in range(len(cover)):
        count = 0
        # TODO: This functional can probably still be improved by using something that takes advantage of the sparsity
        for item in odf[:,i]:
            if item[0,0] > 1/2.0:
                count += 1
        rv += [count/cover.subgraph(i).vcount()]
    return rv

def out_degree_fraction(cover, weights=None, allow_nan = False):
    '''
    Out Degree Fraction (ODF) of a node in a cluster is the ratio between its number of external (boundary) edges
    and its internal edges.
    '''
    w_attr, remove = __get_weight_attr(cover.graph, 'out_degree_fraction', weights)
    mode = "nan" if allow_nan else 0

    #do this outside the loop because it is computationally expensive
    membership = cover.membership
    external_edges = cover.external_edges()
    degree_per_node = cover.graph.strength(weights=w_attr)
    # Intialize return value
    rv = dok_matrix((cover.graph.vcount(), len(cover))) # Rows = Vertex, cols = Cover
    for i in range(len(cover)):
        ext_edge_per_node = dok_matrix((cover.graph.vcount(), 1))

        for edge in external_edges[i]:
            node_index = edge.source if i in membership[edge.source] else edge.target
            ext_edge_per_node[node_index, 0] += 1.0 if weights is None else edge[w_attr]

        for (node, always_zero), ext_edges_for_this_node in ext_edge_per_node.items():
            rv[node, i] += ext_edges_for_this_node/float(degree_per_node[node]) if degree_per_node[node] != 0 else float(mode)

    __remove_weight_attr(cover.graph, w_attr, remove)
    return rv


def external_edges(cover):
    array_of_sets = [ [] for v in cover ]

    # Go through membership array and find nodes in each community
    community_sets = {}
    membership_arrays = cover.membership
    for vertex_id, vertex_communities in enumerate(membership_arrays):
        for community in vertex_communities:
            if community not in community_sets:
                community_sets[community] = set()
            community_sets[community].add(vertex_id)

    # Move from dictionary of communities to array of communities
    # TODO: Maybe we don't have to do this??
    membership_sets = [community_sets[community] for community in sorted(community_sets.keys())]

    for (edge, crossing) in zip(cover.graph.es, cover.crossing()):
        if crossing:
            src,dst = edge.tuple
            for i, membership_set in enumerate(membership_sets):
                #print(i)
                if src in membership_set and dst not in membership_set:
                    array_of_sets[i].append(edge)
                elif dst in membership_set and src not in membership_set:
                    array_of_sets[i].append(edge)

    return array_of_sets


def compare_omega(cover, comparator):
    if(cover is None or comparator is None):
        return None

    score =  omega_index(cover.membership, comparator.membership)
    return score


def compute_metrics(cover, weights=None, ground_truth_cover=None):
    t0 = time.time()

    fomd_results = fomd(cover, weights)
    expansion_results = expansion(cover, weights)
    cut_ratio_results = cut_ratio(cover)
    conductance_results = conductance(cover, weights)
    n_cut_results = normalized_cut(cover, weights)

    # Get out degree fraction results then reuse for max, average, flake
    odf = out_degree_fraction(cover, weights)
    odf = odf.tocsc()
    max_out_results = maximum_out_degree_fraction(cover, odf=odf, weights=weights)
    avg_out_results = average_out_degree_fraction(cover, odf=odf, weights=weights)
    flake_odf_results = flake_out_degree_fraction(cover, odf=odf, weights=weights)
    sep_results = separability(cover,weights)
    results_key = "results"
    agg_key = "aggregations"


    cover.metrics = {
            'Fraction over a Median Degree' : {results_key:fomd_results, agg_key:aggregate(fomd_results)},
            'Expansion'                     : {results_key:expansion_results, agg_key:aggregate(expansion_results)},
            'Cut Ratio'                     : {results_key:cut_ratio_results, agg_key:aggregate(cut_ratio_results)},
            'Conductance'                   : {results_key:conductance_results, agg_key:aggregate(conductance_results)},
            'Normalized Cut'                : {results_key:n_cut_results, agg_key:aggregate(n_cut_results)},
            'Maximum Out Degree Fraction'   : {results_key:max_out_results, agg_key:aggregate(max_out_results)},
            'Average Out Degree Fraction'   : {results_key:avg_out_results, agg_key:aggregate(avg_out_results)},
            'Flake Out Degree Fraction'     : {results_key:flake_odf_results, agg_key:aggregate(flake_odf_results)},
            'Separability'                  : {results_key:sep_results, agg_key:aggregate(sep_results)},
            }

    for i in range(len(cover)):
        sg = cover.subgraph(i)
        sg.compute_metrics(refresh=False)
        #we want to add the metrics from the subgraph calculations to the current cover. The cover and
        #subgraph are essentially the same thing, however because we use the igraph graph functions we
        #can't natively call these call a cover...  hence the need to transfer over the results
        for key, val in sg.metrics.items():
            if key not in cover.metrics:
                cover.metrics[key] = {results_key:[], agg_key:None}
            cover.metrics[key][results_key] += [val]
    #aggregate just the results from the subgraph metrics
    for k  in sg.metrics.keys():
        cover.metrics[k][agg_key] = aggregate(cover.metrics[k][results_key])

def print_metrics(cover):

    if cover.metrics == None:
        if cover.graph.is_weighted():
            cover.compute_metrics(weights="weight")
        else:
            cover.compute_metrics()

    key_print_buffer = 40

    for cover_id in range(len(cover)):
        print("\n\nCover {}".format(cover_id))
        for k,v in cover.metrics.items():
            num_dots = key_print_buffer - len(k)
            dot_str = '.' * num_dots
            if(k != "Subgraphs"):
                print("{}{}{}".format(k, dot_str,v[cover_id]))
            else:
                print("Subgraph_____")
                #for k,v in v.items():
                #    print("{}...".format(k))
                for i in v:
                    print(i)

Cover.fraction_over_median_degree = fomd
VertexCover.metrics = None
VertexCover.metrics_stats = None
VertexCover.print_metrics = print_metrics
VertexCover.compare_omega = compare_omega
VertexCover.compute_metrics = compute_metrics
VertexCover.external_edges = external_edges
VertexCover.expansion = expansion
VertexCover.cut_ratio = cut_ratio
VertexCover.conductance = conductance
VertexCover.normalized_cut = normalized_cut
VertexCover._out_degree_fraction = out_degree_fraction
VertexCover.maximum_out_degree_fraction = maximum_out_degree_fraction
VertexCover.average_out_degree_fraction = average_out_degree_fraction
VertexCover.flake_out_degree_fraction = flake_out_degree_fraction
VertexCover.separability = separability

#!/usr/bin/env python

#####################
##
## Version of Contact Map generator that uses the Redland (librdf)
## python bindings
##
#####################

import sys
import os
import argparse

try:
    import RDF
except ImportError:
    print 'This program requires the redland python bindings'
    sys.exit(1)

def sparql(g, query):
    q = RDF.Query(query)
    return q.execute(g)

def n3(u):
    return "<%s>" % u

def binding(g):
    """
    binding(g)

    Return a sequence of (rule, agentA, siteA, agentB, siteB) tuples
    that correspond to binding operations.
    """
    query = """
PREFIX rbmo: <http://purl.org/rbm/rbmo#>

SELECT DISTINCT ?rule ?agentA ?siteA ?agentB ?siteB
WHERE {
    ?rule rbmo:lhs [
        ## the left hand side of a rule has an agent 
        ## with a site bound to nothing
        rbmo:agent ?agentA;
        rbmo:state [
            rbmo:binding rbmo:Nothing;
            rbmo:site ?siteA
        ]
    ]; rbmo:rhs [
        ## the right hand side of a rule has the same
        ## agent with the site bound to something.
        rbmo:agent ?agentA;
        rbmo:state [
            rbmo:binding ?binding;
            rbmo:site ?siteA
        ]
    ] .
    
    ?rule rbmo:lhs [
        ## the left hand side of a rule has an agent 
        ## with a site bound to nothing
        rbmo:agent ?agentB;
        rbmo:state [
            rbmo:binding rbmo:Nothing;
            rbmo:site ?siteB
        ]
    ]; rbmo:rhs [
        ## the right hand side of a rule has the same
        ## agent with the site bound to something.
        rbmo:agent ?agentB;
        rbmo:state [
            rbmo:binding ?binding;
            rbmo:site ?siteB
        ]
    ] .

    ## this filter is necessary to check that the binding
    ## actually is one, that is blank nodes are used to
    ## bind sites
    FILTER isBlank(?binding)

    ## Apply a predictable ordering on the sites so that
    ## edges do not appear twice.
    FILTER (STR(?siteA) < STR(?siteB))
}
"""
    for r in sparql(g, query):
        yield (r["rule"], r["agentA"], r["siteA"], r["agentB"], r["siteB"])

def unbinding(g):
    """
    unbinding(g)

    Return a sequence of (rule, agentA, siteA, agentB, siteB) tuples
    that correspond to unbinding operations.
    """
    query = """
PREFIX rbmo: <http://purl.org/rbm/rbmo#>

SELECT DISTINCT ?rule ?agentA ?siteA ?agentB ?siteB
WHERE {
    ?rule rbmo:lhs [
        ## the left hand side of a rule has the same
        ## agent with the site bound to something.
        rbmo:agent ?agentA;
        rbmo:state [
            rbmo:binding ?binding;
            rbmo:site ?siteA
        ]
    ]; rbmo:rhs [
        ## the right hand side of a rule has an agent 
        ## with a site bound to nothing
        rbmo:agent ?agentA;
        rbmo:state [
            rbmo:binding rbmo:Nothing;
            rbmo:site ?siteA
        ]
    ] .
    
    ?rule rbmo:lhs [
        ## the left hand side of a rule has the same
        ## agent with the site bound to something.
        rbmo:agent ?agentB;
        rbmo:state [
            rbmo:binding ?binding;
            rbmo:site ?siteB
        ]
    ]; rbmo:rhs [
        ## the right hand side of a rule has an agent 
        ## with a site bound to nothing
        rbmo:agent ?agentB; 
        rbmo:state [
            rbmo:binding rbmo:Nothing;
            rbmo:site ?siteB
        ]
    ] .

    ## this filter is necessary to check that the binding
    ## actually is one, that is blank nodes are used to
    ## bind sites
    FILTER isBlank(?binding)

    ## Apply a predictable ordering on the sites so that
    ## edges do not appear twice.
    FILTER (STR(?siteA) < STR(?siteB))
}
"""
    for r in sparql(g, query):
        yield (r["rule"], r["agentA"], r["siteA"], r["agentB"], r["siteB"])

def rewrite(u):
    """
    rewrite(uri)

    Many of the identifier schemes used here are pretty broken and
    don't properly respond to requests for RDF descriptions. Often
    there are alternative ways of getting the information that require
    out of band knowledge. This function has such out of band knowledge
    and rewrites the URI into a suitable form.
    """
    ## identifiers.org is broken and doesn't understand HTTP
    ## content negotiation to get at descriptions of the identifiers
    ## fix it.
    if u.startswith("http://identifiers.org"):
        return u.replace("identifiers.org", "info.identifiers.org")
    return u

def external(g):
    """
    external(graph)

    Try to fetch external resources and try to load them into the graph.
    """
    query = """
PREFIX bqbiol: <http://biomodels.net/biology-qualifiers/>
SELECT DISTINCT ?res WHERE { ?something bqbiol:is ?res }
"""
    resources = [r for r, in sparql(g, query)]
    for r in resources:
        r = rewrite(str(r))
        sys.stderr.write("Loading %s... " % r)
        try:
            ## N.B. we use rapper(1) here because its parser is a
            ## little more forgiving about the rubbish we may get
            ## than the rdflib one. Note that this is also a security
            ## risk since we are forking a program here and no sanity
            ## checking is done on the URI. Use at your own risk.
            fd = os.popen("rapper -o turtle '%s' 2> /dev/null" % r)
            g.load(fd, format="turtle")
            fd.close()
            sys.stderr.write("success\n")
        except Exception, e:
            sys.stderr.write("failed: %s\n" % e)

def label(g, r):
    """
    label(graph, resource)

    try various ways of getting a human readable name for the resource
    by looking at the information in the graph.
    """
    queries = ["""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?label WHERE { %s rdfs:label ?label }
""", """
PREFIX dct: <http://purl.org/dc/terms/>
SELECT DISTINCT ?label WHERE { %s dct:title ?label }
""", """
PREFIX bqbiol: <http://biomodels.net/biology-qualifiers/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?label WHERE { %s bqbiol:is [ rdfs:label ?label ] }
""", """
PREFIX bqbiol: <http://biomodels.net/biology-qualifiers/>
PREFIX dct: <http://purl.org/dc/terms/>
SELECT DISTINCT ?label WHERE { %s bqbiol:is [ dct:title ?label ] }
""", """
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX sbol: <http://sbols.org/v1#>
SELECT DISTINCT ?tides WHERE { %s sbol:nucleotides ?tides }
"""
]
    for q in queries:
        for result in sparql(g, q % n3(r)):
            for k in result:
                return str(result[k])
    return slug(r).rsplit(":", 1)[-1]

def typeof(g, r):
    """
    typeof(graph, resource)

    Try to find a good description of the biological type.
    """
    queries = ["""
PREFIX biopax: <http://www.biopax.org/release/biopax-level3.owl#>
SELECT DISTINCT ?t
WHERE { %s biopax:physicalEntity ?t }
"""]
    for q in queries:
        for result in sparql(g, q % n3(r)):
            for k in result:
                return str(result[k])
    return None

def slug(r):
    """
    slug(resource)

    A fairly brittle way of producing a short local identifier from
    a URI. Good enuf for the TCS example.
    """
    return str(r).rsplit("/", 1)[-1].rsplit("#",1)[-1]
    return s

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Derive a contact map from RBMO flavour RDF.')
    parser.add_argument('-f', metavar='FILENAME', default="-",
                        help='Input filename (default stdin)')
    parser.add_argument('-i', metavar='FORMAT', default='turtle',
                        help='Input format (default turtle)')
    args = parser.parse_args()

    if args.f == '-':
        fd = sys.stdin
        base = "stdin:"
    else:
        fd = open(args.f, "r")
        base = "file://" + args.f
    data = fd.read()
    fd.close()

    storage = RDF.Storage(storage_name="hashes",
                          name="test",
                          options_string="new='yes',hash-type='memory',dir='.'")
    if storage is None:
        raise Exception("new RDF.Storage failed")

    g = RDF.Model(storage)
    if g is None:
        raise Exception("new RDF.model failed")

    parser=RDF.Parser('raptor')
    if parser is None:
        raise Exception("Failed to create RDF.Parser raptor")

    sys.stderr.write("Parsing URI: %s" % base)
    uri = RDF.Uri(string=base)

    for s in parser.parse_string_as_stream(data, uri):
        g.add_statement(s)

    agents = {}
    sites  = {}
    agent_sites = {}
    rules  = {}

    sys.stderr.write("Calculating bindings...\n")
    bindings = list(binding(g))

    sys.stderr.write("Calculating unbindings...\n")
    unbindings = list(unbinding(g))

    sys.stderr.write("Finding labels and types...\n")
    for rule, agentA, siteA, agentB, siteB in bindings + unbindings:
        if not slug(agentA) in agents:
            agents[slug(agentA)] = (label(g, agentA), typeof(g, agentA))
        if not slug(agentB) in agents:
            agents[slug(agentB)] = (label(g, agentB), typeof(g, agentB))
        if not slug(siteA) in sites:
            sites[slug(siteA)] = (label(g, siteA), typeof(g, siteA))
        if not slug(siteB) in sites:
            sites[slug(siteB)] = (label(g, siteB), typeof(g, siteB))

        asl = agent_sites.setdefault(slug(agentA), [])
        if slug(siteA) not in asl: asl.append(slug(siteA))
        asl = agent_sites.setdefault(slug(agentB), [])
        if slug(siteB) not in asl: asl.append(slug(siteB))

        if not slug(rule) in rules:
            rules[slug(rule)] = label(g, rule)

    rmapfwd = {}
    b_keys = list(set(slug(rule) for rule, _, _, _, _ in bindings))
    u_keys = list(set(slug(rule) for rule, _, _, _, _ in unbindings))
    b_keys.sort(lambda x,y: cmp(rules[x], rules[y]))
    u_keys.sort(lambda x,y: cmp(rules[x], rules[y]))
    rkeys = list(b_keys) + list(u_keys)

    for r in range(0, len(b_keys)):
        rmapfwd[rkeys[r]] = "b%d" % r
    for r in range(0, len(u_keys)):
        rmapfwd[rkeys[r+len(b_keys)]] = "u%d" % r

    sys.stderr.write("Constructing dot file...\n")

    print "graph {"

    for a, sl in agent_sites.items():
        print '    subgraph cluster_%s {' % a.replace("-", "_").replace(":", "_")
        alabel = agents[a][0]
        if agents[a][1]:
            alabel = alabel + " (%s)" % slug(agents[a][1])
        print '        label="%s";' % alabel
        sl.sort()
        for s in sl:
            ss = s.replace(":", "_")
            print '        %s [label="%s"];' % (ss, sites[s][0])
        print '    }'

    for b in bindings:
        r, a1, s1, a2, s2 = map(slug, b)
        l = rmapfwd[r]
        print '    %s -- %s [label="%s"];' % (s1.replace(":", "_"), s2.replace(":", "_"), l)

    for u in unbindings:
        r, a1, s1, a2, s2 = map(slug, u)
        l = rmapfwd[r]
        print '    %s -- %s [label="%s",style=dashed];' % (s1.replace(":", "_"), s2.replace(":", "_"), l)

    l="\\n".join("%s: %s" % (rmapfwd[r], rules[r]) for r in rkeys)
    print '    label="%s";\n}\n' % l

import React, { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

function createGraphData(network) {
  if (!network?.nodes?.length) return { nodes: [], links: [] }

  const nodes = network.nodes.map((node, index) => ({
    ...node,
    color: node.group === 'topic' ? '#f6c86e' : ['#a78bfa', '#5eead4', '#34d399', '#c084fc'][index % 4],
    val: node.group === 'topic' && node.id === 'topic_center' ? 80 : 30,
    ...(node.id === 'topic_center' ? { fx: 0, fy: 0 } : {}),
  }))
  return {
    nodes,
    links: (network.links || []).map((link) => ({ source: link.source, target: link.target })),
  }
}

function drawNode(node, ctx, globalScale) {
  if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return

  const isTopic = node.group === 'topic'
  const isInfluencer = node.group === 'influencer'
  const radius = isTopic ? 17 : isInfluencer ? 9 : 4.5

  ctx.save()
  ctx.translate(node.x, node.y)

  if (isTopic) {
    ctx.beginPath()
    ctx.arc(0, 0, radius + 10, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(246, 200, 110, 0.17)'
    ctx.lineWidth = 2
    ctx.shadowBlur = 20
    ctx.shadowColor = node.color
    ctx.stroke()

    ctx.beginPath()
    ctx.arc(0, 0, radius + 5, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(255, 237, 178, 0.55)'
    ctx.lineWidth = 1.5
    ctx.shadowBlur = 20
    ctx.shadowColor = node.color
    ctx.stroke()

    ctx.beginPath()
    ctx.arc(0, 0, radius, 0, Math.PI * 2)
    ctx.fillStyle = '#f6c86e'
    ctx.shadowBlur = 20
    ctx.shadowColor = node.color
    ctx.fill()

    ctx.beginPath()
    ctx.arc(-radius * 0.28, -radius * 0.3, radius * 0.55, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(255, 250, 218, 0.72)'
    ctx.shadowBlur = 0
    ctx.fill()
  } else {
    ctx.beginPath()
    ctx.arc(0, 0, radius + (isInfluencer ? 5 : 2.5), 0, Math.PI * 2)
    ctx.setLineDash(isInfluencer ? [2, 3] : [])
    ctx.strokeStyle = isInfluencer ? `${node.color}b8` : `${node.color}8c`
    ctx.lineWidth = isInfluencer ? 1.6 : 1
    ctx.shadowBlur = 20
    ctx.shadowColor = node.color
    ctx.stroke()

    ctx.beginPath()
    ctx.arc(0, 0, radius, 0, Math.PI * 2)
    ctx.setLineDash([])
    ctx.fillStyle = node.color
    ctx.shadowBlur = 20
    ctx.shadowColor = node.color
    ctx.fill()

    ctx.beginPath()
    ctx.arc(-radius * 0.25, -radius * 0.3, radius * 0.34, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(225, 255, 249, 0.62)'
    ctx.shadowBlur = 0
    ctx.fill()
  }

  if ((isTopic || isInfluencer) && globalScale > 0.58) {
    const fontSize = Math.max(8 / globalScale, 3)
    ctx.font = `${isTopic ? 600 : 500} ${fontSize}px DM Sans, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = isTopic ? '#fff1bc' : '#d9eee8'
    ctx.shadowBlur = 0
    ctx.fillText(node.label, 0, radius + (isTopic ? 13 : 9) / globalScale)
  }

  ctx.restore()
}

export default function InfluenceGraph({ network }) {
  const graphRef = useRef(null)
  const containerRef = useRef(null)
  const [size, setSize] = useState({ width: 760, height: 430 })
  const graphData = useMemo(() => createGraphData(network), [network])

  useEffect(() => {
    if (!containerRef.current) return undefined

    const observer = new ResizeObserver(([entry]) => {
      const width = Math.max(280, Math.floor(entry.contentRect.width))
      setSize({
        width,
        height: Math.max(360, Math.min(560, Math.floor(width * 0.56))),
      })
    })

    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const graph = graphRef.current
    if (!graph) return

    const charge = graph.d3Force('charge')
    if (charge) {
      charge.strength(-600)
      charge.distanceMax(900)
    }

    const link = graph.d3Force('link')
    if (link) {
      // Fixed: ID was mismatched. Now strictly checks for topic_center.
      link.distance((edge) => (edge.source.id === 'topic_center' ? 170 : 105))
    }

    graph.d3ReheatSimulation()
  }, [])

  return (
    <div
      className="influence-graph"
      ref={containerRef}
      style={{
        position: 'relative',
        zIndex: 50,
        width: '100%',
        pointerEvents: 'auto',
      }}
    >
      <ForceGraph2D
        ref={graphRef}
        graphData={graphData}
        width={size.width}
        height={size.height}
        backgroundColor="rgba(0, 0, 0, 0)"
        nodeCanvasObject={drawNode}
        
        // This is the magic fix that forces the hit-boxes to align with the visual nodes:
        nodePointerAreaPaint={(node, color, ctx) => {
          const isTopic = node.group === 'topic'
          const isInfluencer = node.group === 'influencer'
          const radius = isTopic ? 17 : isInfluencer ? 9 : 4.5
          ctx.fillStyle = color
          ctx.beginPath()
          // Drawing exactly at node.x / node.y on the hidden interaction canvas
          ctx.arc(node.x, node.y, radius + 10, 0, 2 * Math.PI, false)
          ctx.fill()
        }}

        enableNodeDrag={true}
        onNodeDragEnd={(node) => {
          node.fx = node.x
          node.fy = node.y
        }}
        nodeLabel={(node) => `${node.label} · ${node.group}`}
        linkColor={() => 'rgba(255, 255, 255, 0.1)'}
        linkWidth={0.7}
        linkDirectionalParticles={2}
        linkDirectionalParticleWidth={1.5}
        linkDirectionalParticleColor={() => 'rgba(255, 255, 255, 0.8)'}
        linkDirectionalParticleSpeed={0.004}
        d3AlphaDecay={0.018}
        d3VelocityDecay={0.24}
        cooldownTicks={180}
        enableZoomInteraction
        enablePanInteraction
      />
      <div className="graph-legend" style={{ pointerEvents: 'none' }}>
        <span><i className="legend-topic" /> Viral topic</span>
        <span><i className="legend-influencer" /> Primary influencers</span>
        <span><i className="legend-follower" /> Followers</span>
      </div>
    </div>
  )
}

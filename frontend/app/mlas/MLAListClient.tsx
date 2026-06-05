'use client'

import { useState, useMemo } from 'react'
import MLACard from '@/components/MLACard'
import type { MlaListItemEnriched } from '@/types'

interface Props {
  mlas: MlaListItemEnriched[]
  districts: string[]
  parties: string[]
  totalCount: number
}

export default function MLAListClient({ mlas, districts, parties, totalCount }: Props) {
  const [search, setSearch]                   = useState('')
  const [selectedDistrict, setSelectedDistrict] = useState('')
  const [selectedParty, setSelectedParty]     = useState('')

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim()
    return mlas.filter((m) => {
      if (q && !m.name.toLowerCase().includes(q) && !m.constituencyName.toLowerCase().includes(q))
        return false
      if (selectedDistrict && m.district !== selectedDistrict) return false
      if (selectedParty && m.party !== selectedParty) return false
      return true
    })
  }, [mlas, search, selectedDistrict, selectedParty])

  const hasFilters = search !== '' || selectedDistrict !== '' || selectedParty !== ''

  function clearFilters() {
    setSearch('')
    setSelectedDistrict('')
    setSelectedParty('')
  }

  return (
    <div>
      {/* Filter bar */}
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          type="search"
          placeholder="Search by name or constituency…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm
                     shadow-sm outline-none placeholder:text-gray-400
                     focus:border-navy focus:ring-1 focus:ring-navy"
        />
        <select
          value={selectedDistrict}
          onChange={(e) => setSelectedDistrict(e.target.value)}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm
                     outline-none focus:border-navy focus:ring-1 focus:ring-navy"
        >
          <option value="">All Districts</option>
          {districts.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        <select
          value={selectedParty}
          onChange={(e) => setSelectedParty(e.target.value)}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm
                     outline-none focus:border-navy focus:ring-1 focus:ring-navy"
        >
          <option value="">All Parties</option>
          {parties.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        {hasFilters && (
          <button
            onClick={clearFilters}
            className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-500
                       hover:border-gray-300 hover:text-gray-700"
          >
            Clear
          </button>
        )}
      </div>

      {/* Result count */}
      <p className="mb-4 text-sm text-gray-500">
        Showing{' '}
        <span className="font-semibold text-gray-800">{filtered.length}</span> of{' '}
        <span className="font-semibold text-gray-800">{totalCount}</span> MLAs
      </p>

      {/* Grid */}
      {filtered.length === 0 ? (
        <div className="rounded-xl border border-gray-200 py-20 text-center">
          <p className="text-sm text-gray-400">No MLAs match your filters.</p>
          <button
            onClick={clearFilters}
            className="mt-2 text-sm text-navy underline underline-offset-2 hover:text-navy-dark"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {filtered.map((mla) => (
            <MLACard key={mla.id} mla={mla} />
          ))}
        </div>
      )}
    </div>
  )
}

'use client'

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Filler,
  Legend,
} from 'chart.js'
import { Line } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Filler,
  Legend
)

interface EngagementChartProps {
  data: {
    labels: string[]
    datasets: {
      label: string
      data: number[]
      borderColor: string
      backgroundColor: string
    }[]
  }
}

export default function EngagementChart({ data }: EngagementChartProps) {
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        backgroundColor: '#0f172a',
        titleColor: '#94a3b8',
        bodyColor: '#f1f5f9',
        borderColor: 'rgba(255,255,255,0.1)',
        borderWidth: 1,
        padding: 12,
        cornerRadius: 8,
        displayColors: false,
        callbacks: {
          label: (context: any) => ` ${context.parsed.y} Interactions`,
        },
      },
    },
    scales: {
      x: {
        grid: {
          display: false,
        },
        ticks: {
          color: '#475569',
          font: {
            size: 10,
          },
        },
      },
      y: {
        grid: {
          color: 'rgba(255,255,255,0.03)',
        },
        ticks: {
          color: '#475569',
          font: {
            size: 10,
          },
          beginAtZero: true,
        },
      },
    },
  }

  return (
    <div className="h-[300px] w-full">
      <Line options={options} data={data} />
    </div>
  )
}

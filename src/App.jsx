import { useState } from 'react'
import './index.css'  // or whatever path to your CSS file with Tailwind directives
import './App.css'

function App() {
  const [count, setCount] = useState(0)

  return (
<div className="text-blue-50 font-bold">
Hi
</div>
  )
}

export default App

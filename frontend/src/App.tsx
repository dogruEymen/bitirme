import {BrowserRouter, Routes, Route} from 'react-router-dom';
import './App.css'
import Agent from './components/Agent.tsx'
import Dashboard from './components/Dashboard.tsx'
import Settings from './components/Settings.tsx'
import MainLayout from './layouts/MainLayout.tsx'

function App() {


  return (
    <>
	<BrowserRouter>
		<Routes>
			<Route path="/" element={<MainLayout/>}>
				<Route index element={ <Dashboard/> } />
				<Route path="/agent" element={ <Agent/> } />
				<Route path="/settings" element={ <Settings/> } />
			</Route>
		</Routes>
	</BrowserRouter>
    </>
  )
}

export default App
